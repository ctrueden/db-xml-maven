"""
PLAN:
Steal XML and POM code from my other project.
Use Python built-in ElementTree to avoid deps, because it's good enough for this.
Make the POM class more powerful, but without depending on mvn.
In particular, add support for interpolation and dependency reasoning.
Can activate certain profiles as well during interpolation:
- activeByDefault: always
- <os>: yes, evaluate it! err... evaluate it once per supported platform? And have one interpolated POM per platform?
- <jdk>: tricky...
- others: no

Once I have a working interpolated POM parser, I can get project dependencies from it.

Agh, remote resolution is more challenging. Do I want to open that can of worms?
- I think I do... <_<

For dependency reasoning, more challenges:
- transitive dependencies
- dependency exclusions
- It's all doable, though.
- It's tempting to cache dependency lists once computed. But need to watch out for platform-specific deps.

Sources:
- local repo cache -- but might have missing bits that need remote resolution
- actual source repository -- cross-repositories deps still an issue

Code a Maven interface with two different backends?
- Pure Python one, the default. <-- Is this Mini-Maven Python? :-/ Avoids Windows system call woes...?
- One backed by mvn, when more power is needed.

It's feasible to resolve directly from Nexus v2 storage:

    $ ls /opt/sonatype-work/nexus/storage/central/org/scijava/scijava-common/2.93.0/
    scijava-common-2.93.0.jar

    $ ls /opt/sonatype-work/nexus/storage/sonatype-s01/org/scijava/scijava-common/2.94.2
    scijava-common-2.94.2.jar  scijava-common-2.94.2.pom  scijava-common-2.94.2-sources.jar  scijava-common-2.94.2-tests.jar

    $ ls /opt/sonatype-work/nexus/storage/snapshots/org/scijava/scijava-common/2.94.3-SNAPSHOT
    maven-metadata.xml                                        scijava-common-2.94.3-20230706.150124-1.pom
    maven-metadata.xml.md5                                    scijava-common-2.94.3-20230706.150124-1.pom.md5
    maven-metadata.xml.sha1                                   scijava-common-2.94.3-20230706.150124-1.pom.sha1
    scijava-common-2.94.3-20230706.150124-1.jar               scijava-common-2.94.3-20230706.150124-1-sources.jar
    scijava-common-2.94.3-20230706.150124-1.jar.md5           scijava-common-2.94.3-20230706.150124-1-sources.jar.md5
    scijava-common-2.94.3-20230706.150124-1.jar.sha1          scijava-common-2.94.3-20230706.150124-1-sources.jar.sha1
    scijava-common-2.94.3-20230706.150124-1-javadoc.jar       scijava-common-2.94.3-20230706.150124-1-tests.jar
    scijava-common-2.94.3-20230706.150124-1-javadoc.jar.md5   scijava-common-2.94.3-20230706.150124-1-tests.jar.md5
    scijava-common-2.94.3-20230706.150124-1-javadoc.jar.sha1  scijava-common-2.94.3-20230706.150124-1-tests.jar.sha1

This would be nice for performance for some scenarios: run on the same server that hosts the Nexus.

The main wrinkle is that snapshots are *all* timestamped on the remote; there is no copy of the newest snapshot artifacts with non-timestamped names.
"""

import os
import re
import subprocess
from datetime import datetime
from hashlib import md5, sha1
from pathlib import Path
from typing import Any, Dict, Optional, List, Sequence, Tuple
from xml.etree import ElementTree

import requests

import io


class Resolver:
    """
    Logic for doing non-trivial Maven-related things, including:
    * downloading and caching an artifact from a remote repository; and
    * interpolating a POM to create a complete, flat version with profiles applied.
    """

    def download(self, artifact: "Artifact") -> Optional[Path]:
        """
        Download an artifact file from a remote repository.
        :param artifact: The artifact for which a local path should be resolved.
        :return: Local path to the saved artifact, or None if the artifact cannot be resolved.
        """
        raise RuntimeError("Unimplemented")

    def interpolate(self, pom_artifact: "Artifact") -> "Artifact":
        raise RuntimeError("Unimplemented")


class SimpleResolver(Resolver):
    """
    A resolver that works by pure Python code.
    Low overhead, but less feature complete than mvn.
    """

    def download(self, artifact: "Artifact") -> Optional[Path]:
        raise RuntimeError("Unimplemented")

    def interpolate(self, pom_artifact: "Artifact") -> "Artifact":
        pom = pom_artifact.component.pom()
        # CTR START HERE do the interpolation ourselves!
        raise RuntimeError("Unimplemented")


class SysCallResolver(Resolver):
    """
    A resolver that works by shelling out to mvn.
    Requires Maven to be installed.
    """

    def __init__(self, mvn_command: Path):
        self.mvn_command = mvn_command

    def download(self, artifact: "Artifact") -> Optional[Path]:
        assert artifact.env.repo_cache
        args = [
            f"-Dmaven.repo.local={artifact.env.repo_cache}"
            f"-DgroupId={artifact.groupId}",
            f"-DartifactId={artifact.artifactId}",
            f"-Dversion={artifact.version}",
            f"-Dpackaging={artifact.packaging}",
        ]
        if artifact.classifier:
            args.append(f"-Dclassifier={artifact.classifier}")
        if artifact.env.remote_repos:
            remote_repos = ",".join(f"{name}::::{url}" for name, url in artifact.env.remote_repos.items())
            args.append(f"-DremoteRepositories={remote_repos}")

        self._mvn("dependency:get", *args)

        # The file should now exist in the local repo cache.
        # CTR FIXME eliminate duplicate logic with Artifact.path method.
        prefix = Path(*artifact.groupId.split("."), artifact.artifactId, artifact.version)
        cached_file = artifact.env.repo_cache / prefix / artifact.filename
        assert cached_file.exists()
        return cached_file

    def interpolate(self, pom_artifact: "Artifact") -> "Artifact":
        assert pom_artifact.env.repo_cache
        output = self._mvn(
            "help:effective-pom",
            "-f", pom_artifact.path,
            f"-Dmaven.repo.local={pom_artifact.env.repo_cache}"
        )
        # CTR START HERE parse output
        raise RuntimeError("Unimplemented")

    def _mvn(self, *args):
        return SysCallResolver._run(self.mvn_command, "-B", "-T8", *args)

    @staticmethod
    def _run(command, *args):
        command_and_args = (command,) + args
        # _logger.debug(f"Executing: {command_and_args}")
        # FIXME: capture stdout and stderr separately.
        # If exit code non-zero, raise exception with stdout+stderr contents.
        # If exit code zero, return stdout only.
        return subprocess.check_output(command_and_args, stderr=subprocess.STDOUT)


class Environment:
    """
    Maven environment.
    * Local repo cache folder.
    * Local repository storage folders.
    * Remote repository name:URL pairs.
    * Artifact resolution mechanism.
    """

    def __init__(
            self,
            repo_cache: Optional[Path] = None,
            local_repos: Optional[List[Path]] = None,
            remote_repos: Optional[Dict[str, str]] = None,
            resolver: Resolver = None,
    ):
        """
        Create a Maven environment.

        :param repo_cache:
            Optional path to Maven local repository cache directory, i.e. destination
            of `mvn install`. Maven typically uses ~/.m2/repository by default.
            This directory is treated as *read-write* by this library, e.g.
            the download() function will store downloaded artifacts there.
            If no local repository cache path is given, Maven defaults will be used
            (M2_REPO environment variable, or ~/.m2/repository by default).
        :param local_repos:
            Optional list of Maven repository storage local paths to check for artifacts.
            These are real Maven repositories, such as those managed by a Sonatype Nexus v2 instance,
            i.e. ultimate destinations of `mvn deploy`, *not* local repository caches!
            These directories are treated as *read-only* by this library.
            If no local repository paths are given, none will be inferred.
        :param remote_repos:
            Optional dict of remote name:URL pairs, with each URL corresponding
            to a remote Maven repository accessible via HTTP/HTTPS.
            If no local repository paths are given, only Maven Central will be used.
        :param resolver:
            Optional mechanism to use for resolving local paths to artifacts.
            By default, the SimpleResolver will be used.
        """
        self.repo_cache: Path = repo_cache or os.environ.get("M2_REPO", Path("~").expanduser() / "m2" / "repository")
        self.local_repos: List[Path] = local_repos.copy() if local_repos else []
        self.remote_repos: Dict[str, str] = remote_repos.copy() if remote_repos else {}
        self.resolver: Resolver = resolver if resolver else SimpleResolver()
        self.resolver.env = self

    def project(self, groupId: str, artifactId: str):
        return Project(self, groupId, artifactId)


class Project:
    """
    This is a G:A.
    """

    def __init__(self, env: Environment, groupId: str, artifactId: str):
        self.env = env
        self.groupId = groupId
        self.artifactId = artifactId

    def component(self, version: str) -> "Component":
        return Component(self, version)

    def metadata(self):
        prefix = Path(*self.groupId.split("."), self.artifactId)
        # CTR FIXME: track down the right maven-metadata-foo.xml amongst
        # repo_cache, local_repos, and downloading it as needed.
        #metadata_path = self.env.repo_cache / prefix / "maven-metadata.xml"
        #return Metadata(metadata_path)
        raise RuntimeError("Unimplemented")

    def release(self, update: bool = True) -> str:
        """
        Get the newest release version of this project.
        """
        raise RuntimeError("Unimplemented")

    def latest(self, update: bool = True) -> str:
        """
        Get the latest SNAPSHOT version of this project.
        """
        raise RuntimeError("Unimplemented")


class Component:
    """
    This is a Project at a particular version -- i.e. a G:A:V.
    One POM per component.
    """

    def __init__(self, project: Project, version: str):
        self.project = project
        self.version = version

    def artifact(self, classifier: str = "", packaging: str = "jar") -> "Artifact":
        return Artifact(self, classifier, packaging)

    def pom(self) -> "POM":
        return POM(self.artifact(packaging="pom").path)

    @property
    def env(self) -> Environment:
        return self.project.env

    @property
    def groupId(self) -> str:
        return self.project.groupId

    @property
    def artifactId(self) -> str:
        return self.project.artifactId


class Artifact:
    """
    This is a Component plus classifier and packaging.
    One file per artifact.
    """

    def __init__(self, component: Component, classifier: str = "", packaging: str = "jar"):
        self.component = component
        self.classifier = classifier
        self.packaging = packaging

    @property
    def env(self) -> Environment:
        return self.component.env

    @property
    def groupId(self) -> str:
        return self.component.groupId

    @property
    def artifactId(self) -> str:
        return self.component.artifactId

    @property
    def version(self) -> str:
        return self.component.version

    @property
    def path(self) -> Path:
        prefix = Path(*self.groupId.split("."), self.artifactId, self.version)

        # Check Maven local repository cache first if available.
        if self.env.repo_cache:
            cached_file = self.env.repo_cache / prefix / self.filename
            if cached_file.exists():
                return cached_file

        # Check locally available Maven repository storage directories, if any.
        for base in self.env.local_repos:
            # CTR FIXME: Be smarter than this when version is a SNAPSHOT,
            # because local repo storage has timestamped SNAPSHOT filenames.
            p = base / prefix / self.filename
            if p.exists():
                return p

        # Artifact was not found locally; need to download it.
        return self.env.resolver.download(self)

    def md5(self) -> str:
        return self._checksum("md5", md5)

    def sha1(self) -> str:
        return self._checksum("sha1", sha1)

    @property
    def filename(self) -> str:
        classifier_suffix = f"-{self.classifier}" if self.classifier else ""
        return f"{self.artifactId}-{self.version}{classifier_suffix}.{self.packaging}"

    def _checksum(self, suffix, func):
        p = self.path
        checksum_path = p.parent / f"{p.name}.{suffix}"
        return io.text(checksum_path) or func(io.binary(p)).hexdigest()


class Dependency:
    """
    This is an Artifact with scope, optional flag, and exclusions list.
    """

    def __init__(self, artifact: Artifact, scope: str = "compile", optional: bool = False,
                 exclusions: Sequence[Project] = None):
        self.artifact = artifact
        self.scope = scope
        self.optional = optional
        self.exclusions: Tuple[Project] = tuple() if exclusions is None else tuple(exclusions)

    @property
    def env(self) -> Environment:
        return self.artifact.env


class XML:

    def __init__(self, source):
        self.source = source
        self.tree = ElementTree.parse(source)
        XML._strip_ns(self.tree.getroot())

    def elements(self, path: str) -> List[ElementTree.Element]:
        return self.tree.findall(path)

    def value(self, path: str) -> Optional[str]:
        elements = self.elements(path)
        assert len(elements) <= 1
        return elements[0].text if len(elements) > 0 else None

    @staticmethod
    def _strip_ns(el: ElementTree.Element) -> None:
        """
        Remove namespace prefixes from elements and attributes.
        Credit: https://stackoverflow.com/a/32552776/1207769
        """
        if el.tag.startswith("{"):
            el.tag = el.tag[el.tag.find("}") + 1:]
        for k in list(el.attrib.keys()):
            if k.startswith("{"):
                k2 = k[k.find("}") + 1:]
                el.attrib[k2] = el.attrib[k]
                del el.attrib[k]
        for child in el:
            XML._strip_ns(child)


class POM(XML):
    """
    Convenience wrapper around a Maven POM XML document.
    """

    @property
    def groupId(self) -> Optional[str]:
        return self.value("groupId") or self.value("parent/groupId")

    @property
    def artifactId(self) -> Optional[str]:
        return self.value("artifactId")

    @property
    def version(self) -> Optional[str]:
        return self.value("version") or self.value("parent/version")

    @property
    def description(self) -> Optional[str]:
        return self.value("description")

    @property
    def scmURL(self) -> Optional[str]:
        return self.value("scm/url")

    @property
    def issuesURL(self) -> Optional[str]:
        return self.value("issueManagement/url")

    @property
    def ciURL(self) -> Optional[str]:
        return self.value("ciManagement/url")

    @property
    def developers(self) -> List[Dict[str, Any]]:
        devs = []
        for el in self.elements("developers/developer"):
            dev: Dict[str, Any] = {}
            for child in el:
                if len(child) == 0:
                    dev[child.tag] = child.text
                else:
                    if child.tag == 'properties':
                        dev[child.tag] = {grand.tag: grand.text for grand in child}
                    else:
                        dev[child.tag] = [grand.text for grand in child]
            devs.append(dev)
        return devs


class Metadata(XML):
    """
    Convenience wrapper around a maven-metadata.xml document.
    """

    @property
    def groupId(self) -> Optional[str]:
        return self.value("groupId")

    @property
    def artifactId(self) -> Optional[str]:
        return self.value("artifactId")

    @property
    def lastUpdated(self) -> Optional[int]:
        result = self.value("versioning/lastUpdated")
        return None if result is None else int(result)

    @property
    def latest(self) -> Optional[str]:
        # WARNING: The <latest> value is often wrong, for reasons I don't know.
        # However, the last <version> under <versions> has the correct value.
        # Consider using lastVersion instead of latest.
        return self.value("versioning/latest")

    @property
    def lastVersion(self) -> Optional[str]:
        vs = self.elements("versioning/versions/version")
        return None if len(vs) == 0 else vs[-1].text

    @property
    def release(self) -> Optional[str]:
        return self.value("versioning/release")


# -- Functions --

def ts2dt(ts: str) -> datetime:
    """
    Converts Maven-style timestamp strings into Python datetime objects.

    Valid forms:
    * 20210702144918 (seen in <lastUpdated> in maven-metadata.xml)
    * 20210702.144917 (seen in deployed SNAPSHOT filenames)
    """
    m = re.match("(\\d{4})(\\d\\d)(\\d\\d)\\.?(\\d\\d)(\\d\\d)(\\d\\d)", ts)
    if not m:
        raise ValueError(f"Invalid timestamp: {ts}")
    return datetime(*map(int, m.groups()))  # noqa
