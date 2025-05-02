#!/bin/bash

# Check if the correct number of arguments is provided
if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <folder_path> <output_file> [--exclude-empty-lines]"
    exit 1
fi

FOLDER_PATH="$1"
OUTPUT_FILE="$2"
EXCLUDE_EMPTY_LINES=false

# Check if the optional parameter to exclude empty lines is provided
if [ "$3" == "--exclude-empty-lines" ]; then
    EXCLUDE_EMPTY_LINES=true
fi

# Validate that the folder exists
if [ ! -d "$FOLDER_PATH" ]; then
    echo "Error: Folder '$FOLDER_PATH' does not exist."
    exit 1
fi

# Validate that the output file does not already exist
if [ -e "$OUTPUT_FILE" ]; then
    echo "Error: Output file '$OUTPUT_FILE' already exists."
    exit 1
fi

# Combine all files in the folder into the output file
if [ "$EXCLUDE_EMPTY_LINES" = true ]; then
    find "$FOLDER_PATH" -type f -exec cat {} + | grep -v '^$' > "$OUTPUT_FILE"
else
    find "$FOLDER_PATH" -type f -exec cat {} + > "$OUTPUT_FILE"
fi

echo "Files in '$FOLDER_PATH' have been merged into '$OUTPUT_FILE'."