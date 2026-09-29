#!/bin/zsh
# Build the Touch ID helpers (macOS): brainmail, the gate in front of the
# mail password, and brainconfirm, a bare "is it her?" check.
#
#     zsh brain/tools/make_brainmail.sh                 # both
#     zsh brain/tools/make_brainmail.sh brainconfirm    # just one
#
# The Keychain trusts brainmail's exact build. After rebuilding brainmail,
# run `email_send.py touchid off` BEFORE and `touchid on` AFTER, or the first
# read shows a macOS dialog; answering it "Always Allow" also re-trusts it.
# brainconfirm touches no secret and can be rebuilt freely.
set -e
DIR="${0:A:h}"
cd "$DIR"
mkdir -p .bin
for t in ${@:-brainmail brainconfirm}; do
  swiftc -O -o .bin/$t $t.swift
  codesign --force --sign - .bin/$t
  codesign --verify .bin/$t
  print "Built $DIR/.bin/$t"
done
