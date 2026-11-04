#!/usr/bin/env python3
"""PreToolUse guard for the cloud VM. Tickets, PDFs and web pages are untrusted input, and a
cloud session acts with a person's GitHub identity, so what must stay a human decision is
refused here and not left to the model: merging, writing to the release branches, and changing
the CI workflows, which run on a self-hosted machine.

One merge is let through, for a ticket a person tagged `auto-merge`: mcp__github__merge_pull_request,
when GitHub itself says the pull request is open, not a draft, from a feat/ or fix/ branch into dev,
and every check run of its last commit passed. The guard cannot see the ClickUp tag: the skill
checks it, and GitHub branch protection stays the hard limit.

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
# The whole command must match: any other text can hide a value from a check that reads text.
HOOK_SETTING_READ = re.compile(r'git config( --system| --get| --show-origin| --show-scope)* core\.hooksPath')
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

AUTO_MERGE_TOOL = 'mcp__github__merge_pull_request'
AUTO_MERGE_BASE = 'dev'
AUTO_MERGE_HEADS = ('feat/', 'fix/')
PASSED_CONCLUSIONS = ('success', 'neutral', 'skipped')

GITHUB_FORBIDDEN_TOOLS = ('merge', 'push_files', 'create_or_update_file', 'delete_file', 'run_workflow', 'run_trigger', 'create_repository', 'fork_repository')

MERGE_REASON = 'Merging stays with a person, after review.'
AUTO_MERGE_REASON = ('Only an auto-merge is allowed: mcp__github__merge_pull_request on an open pull request from a '
                     'feat/ or fix/ branch into dev, with every check run of its last commit passed. ')
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


def github_get(path):
    result = subprocess.run(['gh', 'api', path], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[:200] or 'gh api failed')
    return json.loads(result.stdout)


def auto_merge_problem(tool_input):
    """What keeps this pull request from an auto-merge, read from GitHub, or None."""
    owner, repo, number = tool_input.get('owner'), tool_input.get('repo'), tool_input.get('pullNumber')
    name = re.compile(r'^[A-Za-z0-9_.-]+$')
    if not (isinstance(owner, str) and isinstance(repo, str) and name.match(owner) and name.match(repo)):
        return 'owner and repo are missing.'
    if not str(number).isdigit():
        return 'pullNumber is missing.'

    try:
        pull = github_get(f'repos/{owner}/{repo}/pulls/{number}')
        sha = pull['head']['sha']
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            return 'the head commit is unreadable.'
        runs = github_get(f'repos/{owner}/{repo}/commits/{sha}/check-runs?per_page=100')
    except (RuntimeError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        return f'GitHub could not be read: {error}'

    if pull.get('state') != 'open' or pull.get('draft'):
        return 'the pull request is not open, or is a draft.'
    if pull.get('base', {}).get('ref') != AUTO_MERGE_BASE:
        return f'the base is not {AUTO_MERGE_BASE}.'
    if not pull.get('head', {}).get('ref', '').startswith(AUTO_MERGE_HEADS):
        return 'the branch is not a feat/ or fix/ branch.'
    if pull.get('head', {}).get('repo', {}).get('full_name') != f'{owner}/{repo}':
        return 'the branch comes from a fork.'

    check_runs = runs.get('check_runs') or []
    if not check_runs or runs.get('total_count', 0) > len(check_runs):
        return 'the check runs of the last commit are missing or too many to read.'
    for run in check_runs:
        if run.get('status') != 'completed' or run.get('conclusion') not in PASSED_CONCLUSIONS:
            return f'the check {run.get("name")} has not passed.'
    return None


def check_bash(command, directory):
    if MERGE.search(command):
        deny(MERGE_REASON)
    if SKIP_GIT_HOOK.search(command) and not HOOK_SETTING_READ.fullmatch(command.strip()):
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

    if tool == AUTO_MERGE_TOOL:
        problem = auto_merge_problem(tool_input)
        if problem:
            deny(AUTO_MERGE_REASON + 'Refused because ' + problem)
        return
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
