#!/bin/bash

# Repository to be cloned
REPO_URL="https://github.com/cosmos/chain-registry.git"

# Directory where the repository will be cloned
CLONE_DIR="chain-registry"

# Clone the repository
git clone $REPO_URL $CLONE_DIR

# Change to the repository directory
cd $CLONE_DIR

# Loop through the directories and print the date of the first commit along with the folder name
for dir in */ ; do
    # Remove the trailing slash
    dir_name=${dir%/}
    # Get the first commit date for the directory
    first_commit_date=$(git log --format="%ai" -- "$dir" | tail -1)
    # Print out the date and folder name
    echo "$first_commit_date - $dir_name"
done | sort -r
