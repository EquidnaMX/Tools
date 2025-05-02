#!/bin/bash

targetDir="${1:-$(pwd)}"

# Find files with only empty lines or whitespace and delete them
find "$targetDir" -type f -exec sh -c '[ -z "$(grep -v "^[[:space:]]*$" "$1")" ] && rm "$1"' _ {} \;

echo "Files with only empty lines or whitespace in the target directory have been deleted."