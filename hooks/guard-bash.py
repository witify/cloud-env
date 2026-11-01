#!/usr/bin/env python3
"""PreToolUse guard for the cloud VM. Tickets, PDFs and web pages are untrusted input, and a
cloud session acts with a person's GitHub identity, so what must stay a human decision is
refused here and not left to the model: merging, writing to the release branches, and changing
the CI workflows, which run on a self-hosted machine.

This stops mistakes and casual injections. It reads command text, so git-hooks/pre-push backs it
up on real pushes, and only GitHub branch protection is a hard limit."""
import json
import re
import shlex
import subprocess
import sys

PROTECTED_BRANCHES = ('dev', 'main', 'master', 'deploy', 'deploy-dev')
PROTECTED_PATTERN = '|'.join(PROTECTED_BRANCHES)

GIT_PUSH = r'\bgit(\s+-[cC]\s+\S+|\s+--\S+)*\s+push\b'
PUSH = re.compile(GIT_PUSH)
PUSH_TO_PROTECTED = re.compile(GIT_PUSH + r'[^|;&]*[\s:+"\'](refs/heads/)?(' + PROTECTED_PATTERN + r')(["\'\s;)]|$)')
PUSH_DELETE = re.compile(GIT_PUSH + r'[^|;&]*(\s--delete\b|\s-d\s|\s:\S)')
PUSH_EVERYTHING = re.compile(GIT_PUSH + r'[^|;&]*\s--(all|mirror)\b')
SKIP_GIT_HOOK = re.compile(r'\bgit\b[^|;&]*\s(--no-verify|-n\b.*\bpush)|core\.hookspath', re.IGNORECASE)
MERGE = re.compile(r'\bgh\s+pr\s+merge\b')
WORKFLOW_FILE = re.compile(r'(^|/)\.github/workflows/')
WORKFLOW_WRITE = re.compile(r'(>|\btee\b|\bsed\s+-i\b|\bmv\b|\bcp\b|\brm\b|\bgit\s+rm\b)[^|;&]*\.github/workflows/')
GUARD_FILE = re.compile(r'^/opt/cloud-env/|^/root/\.claude/')

GH_API_FORBIDDEN_PATH = re.compile(
    r'/merge\b|/merges\b|/git/(refs|commits|trees|blobs)\b|/contents/|/dispatches\b|/rulesets\b|/protection\b'
    r'|/hooks\b|/actions/(secrets|variables|permissions|runners)\b|/keys\b|/collaborators\b|/transfer\b'
)
GH_API = re.compile(r'\bgh\s+api\b')
GH_API_BODY_FLAGS = ('--field', '--raw-field', '--input')
GH_API_FLAGS_WITH_VALUE = 'qtHp'
SHELL_SEPARATORS = set(';|&()<>')

GITHUB_FORBIDDEN_TOOLS = ('merge', 'push_files', 'create_or_update_file', 'delete_file', 'run_workflow', 'run_trigger', 'create_repository', 'fork_repository')

MERGE_REASON = 'Merging stays with a person, after review.'
BRANCH_REASON = 'Push to a feature branch. The release branches change only through a merged pull request.'
DELETE_REASON = 'Branch deletion stays with a person.'
WORKFLOW_REASON = 'CI workflows run on a self-hosted machine: a change there needs a person. Say what must change in the report.'
HOOK_REASON = 'The git hooks of this VM stay on.'
GUARD_REASON = 'The guard of this VM is not editable from a session. Say what must change in the report.'
GITHUB_REASON = 'Write with git on a feature branch and open a pull request. This call goes around the push rules.'


def deny(reason):
    print(json.dumps({
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': 'deny',
            'permissionDecisionReason': reason,
        }
    }))
    sys.exit(0)


def current_branch(directory):
    result = subprocess.run(['git', '-C', directory or '.', 'branch', '--show-current'], capture_output=True, text=True)
    return result.stdout.strip()


def gh_api_is_write(arguments):
    method = None
    has_body = False

    def value_after(index):
        return arguments[index + 1] if index + 1 < len(arguments) else 'GET'

    for index, argument in enumerate(arguments):
        if argument.startswith('--'):
            name, _, value = argument.partition('=')
            if name in GH_API_BODY_FLAGS:
                has_body = True
            elif name == '--method':
                method = value or value_after(index)
        elif argument.startswith('-'):
            # Short flags can be joined, as in -if a=b or -iXPUT.
            for position, flag in enumerate(argument[1:], start=1):
                if flag in 'fF':
                    has_body = True
                    break
                if flag == 'X':
                    method = argument[position + 1:] or value_after(index)
                    break
                if flag in GH_API_FLAGS_WITH_VALUE:
                    break

    # With -X GET, gh sends the fields as a query string.
    return method.upper() != 'GET' if method else has_body


def shell_segments(command):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        tokens = list(lexer)
    except ValueError:
        return [segment.split() for segment in re.split(r'[|;&]+', command)]

    segments, current = [], []
    for token in tokens:
        if token and set(token) <= SHELL_SEPARATORS:
            segments.append(current)
            current = []
        else:
            current.append(token)
    segments.append(current)
    return segments


def gh_api_arguments(segment):
    for index, token in enumerate(segment[:-1]):
        if token.rsplit('/', 1)[-1] == 'gh' and segment[index + 1] == 'api':
            return segment[index + 2:]
    return None


def check_gh_api(command):
    for segment in shell_segments(command):
        arguments = gh_api_arguments(segment)
        if arguments is not None and gh_api_is_write(arguments):
            text = ' '.join(arguments)
            if GH_API_FORBIDDEN_PATH.search(text):
                deny(MERGE_REASON if '/merge' in text else GITHUB_REASON)
        # A quoted command, as in bash -c "gh api ...".
        for token in segment:
            if token != command and GH_API.search(token):
                check_gh_api(token)


def check_bash(command, directory):
    if MERGE.search(command):
        deny(MERGE_REASON)
    if SKIP_GIT_HOOK.search(command):
        deny(HOOK_REASON)
    if PUSH_DELETE.search(command):
        deny(DELETE_REASON)
    if PUSH_TO_PROTECTED.search(command) or PUSH_EVERYTHING.search(command):
        deny(BRANCH_REASON)
    if WORKFLOW_WRITE.search(command):
        deny(WORKFLOW_REASON)
    if PUSH.search(command) and current_branch(directory) in PROTECTED_BRANCHES:
        deny(BRANCH_REASON)
    check_gh_api(command)


def main():
    event = json.load(sys.stdin)
    tool = event.get('tool_name', '')
    tool_input = event.get('tool_input') or {}

    if tool.startswith('mcp__github__') and any(name in tool for name in GITHUB_FORBIDDEN_TOOLS):
        deny(MERGE_REASON if 'merge' in tool else GITHUB_REASON)
    if tool in ('Edit', 'Write', 'NotebookEdit'):
        path = tool_input.get('file_path') or tool_input.get('notebook_path') or ''
        if WORKFLOW_FILE.search(path):
            deny(WORKFLOW_REASON)
        if GUARD_FILE.search(path):
            deny(GUARD_REASON)
    if tool == 'Bash':
        check_bash(tool_input.get('command', ''), event.get('cwd'))


if __name__ == '__main__':
    main()
