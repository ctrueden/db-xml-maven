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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Sequence
from xml.etree import ElementTree as ET


# TODO: resolvers extend common base interface?

# What does "resolve" mean?
# Just means getting the path to a local file *somewhere*.
# So... the SimpleResolver will use requests to download from a remote repository via HTTPS.
# The LocalNexusResolver will just look into the directories given.

class Resolver:
    def __init__(self, env: "Environment"):
        self.env = env

    def resolve(self, artifact: "Artifact") -> Optional[Path]:
        """
        Get a file path to the artifact.
        :param artifact: The artifact for which a path should be resolved.
        :return: The resolved path, or None if the artifact cannot be resolved.
        """
        raise RuntimeError("Unimplemented")

    def effective_pom(self, pom: "Artifact") -> "Artifact":
        raise RuntimeError("Unimplemented")


class SimpleResolver(Resolver):
    """
    A resolver that works by pure Python code.
    Low overhead, but less feature complete than mvn.
    """
    def __init__(self, env: "Environment"):
        Resolver.__init__(self, env)

    def resolve(self, artifact: "Artifact") -> Optional[Path]:
        raise RuntimeError("Unimplemented")

    def effective_pom(self, pom: "Artifact") -> "Artifact":
        raise RuntimeError("Unimplemented")


class LocalRepositoryResolver:
    """
    """
    def __init__(self, env: "Environment", dirs: Sequence[Path]):
        self.dirs = []
        self.dirs.append(dirs)


import subprocess


class SysCallResolver:
    """
    A resolver that works by shelling out to mvn.
    Requires Maven to be installed, obviously.
    """

    # Random tips:
    # * The exec:exec echo trick also works with -f flag.

    def __init__(self, env: "Environment", mvn_command: Path):
        self.env = env
        self.mvn_command = mvn_command

    def resolve(self, artifact: "Artifact") -> Optional[Path]:
        """
        :param artifact:
        :return:
        """

        # Check local repository storage for the artifact.
        for local_repo in self.env.local_repos:
            pass
        raise RuntimeError("Unimplemented")

    def effective_pom(self, pom: "Artifact") -> "Artifact":
        pom_path = self.resolve(pom)
        self._mvn("help:effective-pom", "-f", pom_path)
        raise RuntimeError("Unimplemented")

    def _mvn(self, *args):
        mvn_command_and_args = [self.mvn_command, "-B", "-T8"]

        if self.env.local_repos:
            # NB: Assume the first local_repo entry is the canonical one for mvn to use.
            # FIXME: Need to distinguish between local paths that are *repo caches*
            # versus those that are *Nexus storage directories*. We don't want mvn to
            # write anything into Nexus storage directories by treating them as local repos caches.
            mvn_command_and_args.append(f"-Dmaven.repo.local={self.env.local_repos[0]}")

        return SysCallResolver._run(*mvn_command_and_args)

    def _maven_repo_local(self) -> Optional[str]:
        """Local repository cache directory override for -Dmaven.repo.local."""

    def _remote_repositories(self) -> Optional[str]:
        """
        Repositories in the format id::[layout]::url, separated by comma.
        Needed e.g. for mvn's dependency:get goal.
        """
        return (
            ",".join(f"{name}::::{url}" for name, url in self.env.remote_repos.items())
            if self.env.remote_repos
            else None
        )

    @staticmethod
    def _run(command, *args):
        command_and_args = (command,) + args
        #_logger.debug(f"Executing: {command_and_args}")
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
            Optional path to Maven local repository cache directory, i.e. a destination
            of `mvn install`. Maven typically uses ~/.m2/repository by default.
            This directory is treated as *read-write* by this library, e.g.
            the resolve() function will store downloaded artifacts here.
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
        self.resolver: Resolver = SysCallResolver(self, "mvn") # CTR FIXME use SimpleResolver once it is implemented. And don't hardcode relative `mvn` executable either!

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

    def pom(self) -> "Artifact":
        return self.artifact(packaging="pom")

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
        # Check Maven local repository cache first if available.
        # Then check local Maven repository storage directories, if any.
        bases = []
        if self.env.repo_cache:
            bases.append(self.env.repo_cache)
        bases.extend(self.env.local_repos)
        prefix = Path(*self.groupId.split("."), self.artifactId, self.version)
        for base in bases:
            dir = base / prefix
            p = dir / self.filename()
            # CTR FIXME: Be smarter than this when version is a SNAPSHOT,
            # because local repo storage has timestamped filenames.
            if p.exists():
                return p

        # Artifact was not found locally; need to invoke the resolver.
        return self.env.resolver.resolve(self)

    def md5(self) -> str:
        #return "d378517ad2287c148f60327caca4956e966f6ba4"
        raise RuntimeError("Unimplemented")

    def sha1(self) -> str:
        #return "d378517ad2287c148f60327caca4956e966f6ba4"
        raise RuntimeError("Unimplemented")

    def timestamp(self) -> str:
        #return "20210915210749"
        raise RuntimeError("Unimplemented")

    def filename(self) -> str:
        classifier_suffix = f"-{self.classifier}" if self.classifier else ""
        return f"{self.artifactId}-{self.version}{classifier_suffix}.{self.packaging}"

    def filesize(self) -> int:
        #return 12893
        raise RuntimeError("Unimplemented")


class Dependency:
    """
    This is an Artifact with scope, optional flag, and exclusions list.
    """

    def __init__(self, artifact: Artifact, scope: str = "compile", optional: bool = False, exclusions: Sequence[Project] = None):
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
        self.tree = ET.parse(source)
        XML._strip_ns(self.tree.getroot())

    def elements(self, path: str) -> List[ET.Element]:
        return self.tree.findall(path)

    def value(self, path: str) -> Optional[str]:
        el = self.elements(path)
        assert len(el) <= 1
        return None if len(el) == 0 else el[0].text

    @staticmethod
    def _strip_ns(el: ET.Element) -> None:
        """
        Remove namespace prefixes from elements and attributes.
        Credit: https://stackoverflow.com/a/32552776/1207769
        """
        if el.tag.startswith("{"):
            el.tag = el.tag[el.tag.find("}")+1:]
        for k in list(el.attrib.keys()):
            if k.startswith("{"):
                k2 = k[k.find("}")+1:]
                el.attrib[k2] = el.attrib[k]
                del el.attrib[k]
        for child in el:
            XML._strip_ns(child)

class MavenPOM(XML):
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

    def interpolate(self, env) -> "POM":
        """
        Recursively parse ancestor POMs and integrate them.
        """
        # TODO: Decide where this function should actually live.
        raise RuntimeError("Unimplemented")


class MavenMetadata(XML):

    @property
    def groupId(self) -> Optional[str]:
        try:
            return self.value("groupId")
        except Exception:
            return self.value("parent/groupId")

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
    m = re.match("(\d{4})(\d\d)(\d\d)\.?(\d\d)(\d\d)(\d\d)", ts)
    if not m: raise ValueError(f"Invalid timestamp: {ts}")
    return datetime(*map(int, m.groups())) #noqa
