<?php

// Prints the string in the project's install command or seeders that is the password of this hash,
// and exits 1 when none is. The password stays in each project, so this public repository never holds
// it, and a guess that does not match never reaches an agent. Run from the project's root.
// The characters allowed here are safe inside the single quotes of the file that keeps the result.

const STRING_LITERAL = '/[\'"]([A-Za-z0-9_!@#%^&*.,:;+=?~-]{4,64})[\'"]/';
const SEARCH_SECONDS = 20;

$hash = $argv[1] ?? '';
$deadline = microtime(true) + SEARCH_SECONDS;
$checked = [];

$files = array_merge(
    glob('src/App/Console/Commands/Install.php') ?: [],
    glob('app/Console/Commands/Install.php') ?: [],
    glob('database/seeders/*.php') ?: [],
    glob('database/factories/UserFactory.php') ?: [],
);

foreach ($files as $file) {
    preg_match_all(STRING_LITERAL, (string) file_get_contents($file), $matches);

    foreach ($matches[1] as $candidate) {
        if (isset($checked[$candidate])) {
            continue;
        }
        $checked[$candidate] = true;

        if (password_verify($candidate, $hash)) {
            echo $candidate;
            exit(0);
        }

        if (microtime(true) > $deadline) {
            exit(1);
        }
    }
}

exit(1);
