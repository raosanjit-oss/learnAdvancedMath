#!/bin/sh
set -eu
umask 077
resources=$(dirname "$0")
support="$HOME/Library/Application Support/Visual Math"
library="$HOME/Movies/Visual Math"
version=$(cat "$resources/runtime-version")
runtime="$support/$version"
mkdir -p "$support" "$library"
if [ ! -d "$runtime" ]; then
    # conda-unpack embeds the absolute path. Keep that folder in place and
    # publish the version symlink only after the installation finishes.
    installation=$(mktemp -d "$support/runtime.XXXXXXXX")
    /usr/bin/tar -xzf "$resources/runtime.tar.gz" -C "$installation"
    "$installation/bin/python" -Es "$installation/bin/conda-unpack"
    if [ ! -d "$runtime" ]; then ln -s "$installation" "$runtime"; fi
fi
physical=$(cd "$runtime" && pwd -P)
exec "$physical/bin/python" -Es "$resources/render_document.py" "$1" "$library"
