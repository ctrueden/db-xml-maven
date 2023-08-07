#!/bin/sh
set -e
cd "$(dirname "$0")"
rm -rf *.pom "$HOME/.m2/repository/org/scijava/jgo/thicket"
python thicket.py
for pom in *.pom
do
  mvn install:install-file -DpomFile="$pom" -Dfile="$pom"
done

mvn_version=$(mvn -B -v 2>&1 | head -n1 | sed 's;.* ;;')
mvn -B help:effective-pom -f thicket.pom | grep '^\( \|<[^!]\)' > "thicket-effective-maven-$mvn_version.pom"
