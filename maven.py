from abc import ABC, abstractmethod
from datetime import datetime
from hashlib import md5, sha1
from itertools import combinations
from os import environ
from pathlib import Path
from re import findall, match
from subprocess import run
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from xml.etree import ElementTree

import requests

import iogo

# -- Constants --

DEFAULT_CLASSIFIER = ""
DEFAULT_PACKAGING = "jar"
DEFAULT_SCOPE = "compile"


# -- Functions --

def ts2dt(ts: str) -> datetime:
    """
    Converts Maven-style timestamp strings into Python datetime objects.

    Valid forms:
    * 20210702144918 (seen in <lastUpdated> in maven-metadata.xml)
    * 20210702.144917 (seen in deployed SNAPSHOT filenames and <snapshotVersion><value>)
    """
    m = match("(\\d{4})(\\d\\d)(\\d\\d)\\.?(\\d\\d)(\\d\\d)(\\d\\d)", ts)
    if not m: raise ValueError(f"Invalid timestamp: {ts}")
    return datetime(*map(int, m.groups()))  # noqa


def coord2str(
    groupId: str,
    artifactId: str,
    version: str = None,
    classifier: str = None,
    packaging: str = None,
    scope: str = None,
    optional: bool = False
):
    # We match the order from the dependency:list goal: G:A:P:C:V:S.
    s = f"{groupId}:{artifactId}"
    if packaging: s += f":{packaging}"
    if classifier: s += f":{classifier}"
    if version: s += f":{version}"
    if scope: s += f":{scope}"
    if optional: s += " (optional)"
    return s


# -- Classes --

class Resolver(ABC):
    """
    Logic for doing non-trivial Maven-related things, including:
    * downloading and caching an artifact from a remote repository; and
    * determining the dependencies of a particular Maven component.
    """

    @abstractmethod
    def download(self, artifact: "Artifact") -> Optional[Path]:
        """
        Download an artifact file from a remote repository.
        :param artifact: The artifact for which a local path should be resolved.
        :return: Local path to the saved artifact, or None if the artifact cannot be resolved.
        """
        ...

    @abstractmethod
    def dependencies(self, component: "Component") -> List["Dependency"]:
        """
        Determine dependencies for the given Maven component.

        :param component: The component for which to determine the dependencies.
        :return: The list of dependencies.
        """
        ...


class SimpleResolver(Resolver):
    """
    A resolver that works by pure Python code.
    Low overhead, but less feature complete than mvn.
    """

    def download(self, artifact: "Artifact") -> Optional[Path]:
        if artifact.version.endswith("-SNAPSHOT"):
            raise RuntimeError("Downloading of snapshots is not yet implemented.")

        for remote_repo in artifact.env.remote_repos:
            # Consider raising an exception for snapshots for the moment?
            url = f"{remote_repo}/{artifact.component.path_prefix}/{artifact.filename}"
            response: requests.Response = requests.get(url)
            if response.status_code == 200:
                # Artifact downloaded successfully.
                # FIXME: Also get MD5 and SHA1 files if available.
                # And for each, if it *is* available and successfully gotten,
                # check the actual hash of the downloaded file contents against the expected one.
                cached_file = artifact.cached_path
                assert not cached_file.exists()
                with open(cached_file, "wb") as f:
                    f.write(response.content)
                return cached_file

        raise RuntimeError(f"Artifact {artifact} not found in remote repositories {artifact.env.remote_repos}")

    def dependencies(self, component: "Component") -> List["Dependency"]:
        model = Model(component.env, component.pom())
        # FIXME: Transitive dependencies?
        return list(model.deps.values())


class SysCallResolver(Resolver):
    """
    A resolver that works by shelling out to mvn.
    Requires Maven to be installed.
    """

    def __init__(self, mvn_command: Path):
        self.mvn_command = mvn_command
        self.mvn_flags = ["-B", "-T8"]

    def download(self, artifact: "Artifact") -> Optional[Path]:
        print(f"[INFO] Downloading artifact: {artifact}")
        assert artifact.env.repo_cache
        assert artifact.groupId
        assert artifact.artifactId
        assert artifact.version
        assert artifact.packaging
        args = [
            f"-Dmaven.repo.local={artifact.env.repo_cache}",
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
        assert artifact.cached_path and artifact.cached_path.exists()
        return artifact.cached_path

    def dependencies(self, component: "Component") -> List["Dependency"]:
        # Invoke the dependency:list goal, direct dependencies only.
        print(f"[DEBUG] Getting dependencies: {component}")
        pom_artifact = component.artifact(packaging="pom")
        assert pom_artifact.env.repo_cache
        output = self._mvn(
            "dependency:list",
            "-f", pom_artifact.resolve(),
            "-DxcludeTransitive=true",
            f"-Dmaven.repo.local={pom_artifact.env.repo_cache}"
        )

        # FIXME: Fix the following logic to parse dependency:list output.

        # Filter to include only the actual lines of XML.
        lines = output.splitlines()
        snip = snap = None
        for i, line in enumerate(lines):
            if snip is None and line.startswith("<?xml"):
                snip = i
            elif line == "</project>":
                snap = i
                break
        assert snip is not None and snap is not None
        pom = POM("\n".join(lines[snip:snap + 1]), pom_artifact.env)

        # Extract the flattened dependencies.
        return pom.dependencies()

    def _mvn(self, *args) -> str:
        # TODO: Windows.
        return SysCallResolver._run(self.mvn_command, *self.mvn_flags, *args)

    @staticmethod
    def _run(command, *args) -> str:
        command_and_args = (command,) + args
        # _logger.debug(f"Executing: {command_and_args}")
        result = run(command_and_args, capture_output=True)
        if result.returncode == 0: return result.stdout.decode()

        error_message = (
            f"Command failed with exit code {result.returncode}:\n"
            f"{command_and_args}"
        )
        if result.stdout: error_message += f"\n\n[stdout]\n{result.stdout.decode()}"
        if result.stderr: error_message += f"\n\n[stderr]\n{result.stderr.decode()}"
        raise RuntimeError(error_message)


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
        self.repo_cache: Path = repo_cache or environ.get("M2_REPO", Path("~").expanduser() / ".m2" / "repository")
        self.local_repos: List[Path] = local_repos.copy() if local_repos else []
        self.remote_repos: Dict[str, str] = remote_repos.copy() if remote_repos else {}
        self.resolver: Resolver = resolver if resolver else SimpleResolver()

    def project(self, groupId: str, artifactId: str) -> "Project":
        return Project(self, groupId, artifactId)

    def dependency(self, el: ElementTree.Element) -> "Dependency":
        groupId = el.findtext("groupId")
        artifactId = el.findtext("artifactId")
        assert groupId and artifactId
        version = el.findtext("version")  # NB: Might be None, which means managed.
        classifier = el.findtext("classifier") or DEFAULT_CLASSIFIER
        packaging = el.findtext("type") or DEFAULT_PACKAGING
        scope = el.findtext("scope") or DEFAULT_SCOPE
        optional = el.findtext("optional") == "true" or False
        exclusions = [
            self.project(ex.findtext("groupId"), ex.findtext("artifactId"))
            for ex in el.findall("exclusions/exclusion")
        ]
        project = self.project(groupId, artifactId)
        artifact = project.at_version(version).artifact(classifier, packaging)
        return Dependency(artifact, scope, optional, exclusions)


class Project:
    """
    This is a G:A.
    """

    def __init__(self, env: Environment, groupId: str, artifactId: str):
        self.env = env
        self.groupId = groupId
        self.artifactId = artifactId

    def __eq__(self, other):
        return (
            self.groupId == other.groupId
            and self.artifactId == other.artifactId
        )

    def __hash__(self):
        return hash((self.groupId, self.artifactId))

    def __str__(self):
        return coord2str(self.groupId, self.artifactId)

    @property
    def path_prefix(self) -> Path:
        """
        Relative directory where artifacts of this project are organized.
        E.g. org.jruby:jruby-core -> org/jruby/jruby-core
        """
        return Path(*self.groupId.split("."), self.artifactId)

    def at_version(self, version: str) -> "Component":
        return Component(self, version)

    def metadata(self) -> "Metadata":
        # Aggregate all locally available project maven-metadata.xml sources.
        repo_cache_dir = self.env.repo_cache / self.path_prefix
        paths = (
            [p for p in repo_cache_dir.glob("maven-metadata*.xml")] +
            [r / self.path_prefix / "maven-metadata.xml" for r in self.env.local_repos]
        )
        return Metadatas([MetadataXML(p) for p in paths if p.exists()])

    def update(self):
        # CTR FIXME: Update metadata from remote sources!
        pass

    def release(self) -> str:
        """
        Get the newest release version of this project.
        This is the equivalent of Maven's RELEASE version.
        """
        raise RuntimeError("Unimplemented")

    def latest(self) -> str:
        """
        Get the latest SNAPSHOT version of this project.
        This is the equivalent of Maven's LATEST version.
        """
        raise RuntimeError("Unimplemented")

    def versions(self, releases: bool = True, snapshots: bool = False, locked: bool = False) -> List["Component"]:
        """
        Get the list of all known versions of this project.

        :param releases:
            If True, include release versions (those not ending in -SNAPSHOT) in the results.
        :param snapshots:
            If True, include snapshot versions (those ending in -SNAPSHOT) in the results.
        :param locked:
            If True, returned snapshot versions will include the timestamp or "lock" flavor of the version strings;
            For example: 2.94.3-20230706.150124-1 rather than 2.94.3-SNAPSHOT.
            As such, there may be more entries returned than when this flag is False.
        :return: List of Component objects, each of which represents a known version.
        """
        # CTR FIXME: Think about whether multiple timestamped snapshots at the same snapshot version should be
        # one Component, or multiple Components. because we could just have a list of timestamps in the Component
        # as a field... but then we probably violate existing 1-to-many vs 1-to-1 type assumptions regarding how Components and Artifacts relate.
        # You can only "sort of" have an artifact for a SNAPSHOT without a timestamp lock... it's always timestamped on the remote side,
        # but on the local side only implicitly unless Maven's snapshot locking feature is used... confusing.
        if locked: raise RuntimeError("Locked snapshot reporting is unimplemented")
        metadata = self.metadata()
        return [
            self.at_version(v)
            for v in metadata.versions
            if (
                (snapshots and v.endswith("-SNAPSHOT")) or
                (releases and not v.endswith("-SNAPSHOT"))
            )
        ]


class Component:
    """
    This is a Project at a particular version -- i.e. a G:A:V.
    One POM per component.
    """

    def __init__(self, project: Project, version: str):
        self.project = project
        self.version = version

    def __eq__(self, other):
        return (
            self.project == other.project
            and self.version == other.version
        )

    def __hash__(self):
        return hash((self.project, self.version))

    def __str__(self):
        return coord2str(self.groupId, self.artifactId, self.version)

    @property
    def env(self) -> Environment:
        return self.project.env

    @property
    def groupId(self) -> str:
        return self.project.groupId

    @property
    def artifactId(self) -> str:
        return self.project.artifactId

    @property
    def path_prefix(self) -> Path:
        """
        Relative directory where artifacts of this component are organized.
        E.g. org.jruby:jruby-core:9.3.3.0 -> org/jruby/jruby-core/9.3.3.0
        """
        return self.project.path_prefix / self.version

    def artifact(self, classifier: str = DEFAULT_CLASSIFIER, packaging: str = DEFAULT_PACKAGING) -> "Artifact":
        return Artifact(self, classifier, packaging)

    def pom(self) -> "POM":
        """
        Get a data structure with the contents of the POM.

        :return: The POM content.
        """
        pom_artifact = self.artifact(packaging="pom")
        return POM(pom_artifact.resolve(), self.env)


class Artifact:
    """
    This is a Component plus classifier and packaging.
    One file per artifact.
    """

    def __init__(self, component: Component, classifier: str = DEFAULT_CLASSIFIER, packaging: str = DEFAULT_PACKAGING):
        self.component = component
        self.classifier = classifier
        self.packaging = packaging

    def __eq__(self, other):
        return (
            self.component == other.component
            and self.classifier == other.classifier
            and self.packaging == other.packaging
        )

    def __hash__(self):
        return hash((self.component, self.classifier, self.packaging))

    def __str__(self):
        return coord2str(self.groupId, self.artifactId, self.version, self.classifier, self.packaging)

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
    def filename(self) -> str:
        """
        Filename portion of the artifact path. E.g.:
        - g=org.python a=jython v=2.7.0 -> jython-2.7.0.jar
        - g=org.lwjgl a=lwjgl v=3.3.1 c=natives-linux -> lwjgl-3.3.1-natives-linux.jar
        - g=org.scijava a=scijava-common v=2.94.2 p=pom -> scijava-common-2.94.2.pom
        """
        classifier_suffix = f"-{self.classifier}" if self.classifier else ""
        return f"{self.artifactId}-{self.version}{classifier_suffix}.{self.packaging}"

    @property
    def cached_path(self) -> Optional[Path]:
        """
        Path to the artifact in the linked environment's local repository cache.
        Might not actually exist! This just returns where it *would be* if present.
        """
        return (
            self.env.repo_cache / self.component.path_prefix / self.filename
            if self.env.repo_cache
            else None
        )

    def resolve(self) -> Path:
        """
        Resolves a local path to the artifact, downloading it as needed:

        1. If present in the linked local repository cache, use that path.
        2. Else if present in a linked locally available repository storage directory, use that path.
        3. Otherwise, invoke the environment's resolver to download it.
        """

        # Check Maven local repository cache first if available.
        cached_file = self.cached_path
        if cached_file and cached_file.exists(): return cached_file

        # Check any locally available Maven repository storage directories.
        for base in self.env.local_repos:
            # CTR FIXME: Be smarter than this when version is a SNAPSHOT,
            # because local repo storage has timestamped SNAPSHOT filenames.
            p = base / self.component.path_prefix / self.filename
            if p.exists(): return p

        # Artifact was not found locally; need to download it.
        return self.env.resolver.download(self)

    def md5(self) -> str:
        return self._checksum("md5", md5)

    def sha1(self) -> str:
        return self._checksum("sha1", sha1)

    def _checksum(self, suffix, func):
        p = self.resolve()
        checksum_path = p.parent / f"{p.name}.{suffix}"
        return iogo.text(checksum_path) or func(iogo.binary(p)).hexdigest()


class Dependency:
    """
    This is an Artifact with scope, optional flag, and exclusions list.
    """

    def __init__(
            self,
            artifact: Artifact,
            scope: str = DEFAULT_SCOPE,
            optional: bool = False,
            exclusions: Iterable[Project] = None
    ):
        self.artifact = artifact
        self.scope = scope
        self.optional = optional
        self.exclusions: Tuple[Project] = tuple() if exclusions is None else tuple(exclusions)

    def __str__(self):
        return coord2str(self.groupId, self.artifactId, self.version, self.classifier, self.type, self.scope, self.optional)

    @property
    def env(self) -> Environment:
        return self.artifact.env

    @property
    def groupId(self) -> str:
        return self.artifact.groupId

    @property
    def artifactId(self) -> str:
        return self.artifact.artifactId

    @property
    def version(self) -> str:
        return self.artifact.version

    @property
    def classifier(self) -> str:
        return self.artifact.classifier

    @property
    def type(self) -> str:
        return self.artifact.packaging

    def set_version(self, version: str) -> None:
        self.artifact.component.version = version


class XML:

    def __init__(self, source: Union[str, Path], env: Optional[Environment] = None):
        self.source = source
        self.env: Environment = env or Environment()
        self.tree: ElementTree.ElementTree = (
            ElementTree.ElementTree(ElementTree.fromstring(source))
            if isinstance(source, str)
            else ElementTree.parse(source)
        )
        XML._strip_ns(self.tree.getroot())

    def dump(self, el: ElementTree.Element = None) -> str:
        return ElementTree.tostring(el if el else self.tree.getroot()).decode()

    def elements(self, path: str) -> List[ElementTree.Element]:
        return self.tree.findall(path)

    def element(self, path: str) -> Optional[ElementTree.Element]:
        els = self.elements(path)
        assert len(els) <= 1
        return els[0] if els else None

    def values(self, path: str) -> List[str]:
        return [el.text for el in self.elements(path)]

    def value(self, path: str) -> Optional[str]:
        return el.text if (el := self.element(path)) else None

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

    def artifact(self) -> Artifact:
        """
        Get an Artifact object representing this POM.
        """
        project = self.env.project(self.groupId, self.artifactId)
        return project.at_version(self.version).artifact(packaging="pom")

    def parent(self) -> Optional["POM"]:
        """
        Get POM data for this POM's parent POM, or None if no parent is declared.
        """
        if not self.element("parent"): return None

        g = self.value("parent/groupId")
        a = self.value("parent/artifactId")
        v = self.value("parent/version")
        assert g and a and v
        relativePath = self.value("parent/relativePath")

        if (
            isinstance(self.source, Path) and
            relativePath and
            (parent_path := self.source / relativePath).exists()
        ):
            # Use locally available parent POM file.
            parent_pom = POM(parent_path, self.env)
            if (
                g == parent_pom.groupId and
                a == parent_pom.artifactId and
                v == parent_pom.version
            ):
                return parent_pom
            print("[DEBUG] Ignoring non-matching GAV for relative parent path: {parent_path}")

        pom_artifact = self.env.project(g, a).at_version(v).artifact(packaging="pom")
        return POM(pom_artifact.resolve(), self.env)

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
        return self._people("developers/developer")

    @property
    def contributors(self) -> List[Dict[str, Any]]:
        return self._people("contributors/contributor")

    def _people(self, path: str) -> List[Dict[str, Any]]:
        people = []
        for el in self.elements(path):
            person: Dict[str, Any] = {}
            for child in el:
                if len(child) == 0:
                    person[child.tag] = child.text
                else:
                    if child.tag == "properties":
                        for grand in child:
                            person[grand.tag] = grand.text
                    else:
                        person[child.tag] = [grand.text for grand in child]
            people.append(person)
        return people

    @property
    def properties(self) -> Dict[str, str]:
        return {el.tag: el.text for el in self.elements("properties/*")}

    def dependencies(self, managed: bool = False) -> List[Dependency]:
        xpath = "dependencies/dependency"
        if managed: xpath = f"dependencyManagement/{xpath}"
        return [
            self.env.dependency(el)
            for el in self.elements(xpath)
        ]


class Metadata(ABC):

    @property
    @abstractmethod
    def groupId(self) -> Optional[str]: ...

    @property
    @abstractmethod
    def artifactId(self) -> Optional[str]: ...

    @property
    @abstractmethod
    def lastUpdated(self) -> Optional[datetime]: ...

    @property
    @abstractmethod
    def latest(self) -> Optional[str]: ...

    @property
    @abstractmethod
    def versions(self) -> List[str]: ...

    @property
    @abstractmethod
    def lastVersion(self) -> Optional[str]: ...

    @property
    @abstractmethod
    def release(self) -> Optional[str]: ...


class MetadataXML(XML, Metadata):
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
    def lastUpdated(self) -> Optional[datetime]:
        value = self.value("versioning/lastUpdated")
        return ts2dt(value) if value else None

    @property
    def latest(self) -> Optional[str]:
        # WARNING: The <latest> value is often wrong, for reasons I don't know.
        # However, the last <version> under <versions> has the correct value.
        # Consider using lastVersion instead of latest.
        return self.value("versioning/latest")

    @property
    def versions(self) -> List[str]:
        return self.values("versioning/versions/version")

    @property
    def lastVersion(self) -> Optional[str]:
        return vs[-1] if (vs := self.versions) else None

    @property
    def release(self) -> Optional[str]:
        return self.value("versioning/release")


class Metadatas(Metadata):
    """
    A unified Maven metadata combined over a collection of individual Maven metadata.
    The typical use case for this class is to aggregate multiple maven-metadata.xml files
    describing the same project, across multiple local repository cache and storage directories.
    """

    def __init__(self, metadatas: Iterable[Metadata]):
        self.metadatas: List[Metadata] = sorted(metadatas, key=lambda m: m.lastUpdated)
        for a, b in combinations(self.metadatas, 2):
            assert a.groupId == b.groupId and a.artifactId == b.artifactId

    @property
    def groupId(self) -> Optional[str]:
        return self.metadatas[0].groupId

    @property
    def artifactId(self) -> Optional[str]:
        return self.metadatas[0].artifactId

    @property
    def lastUpdated(self) -> Optional[datetime]:
        return self.metadatas[-1].lastUpdated

    @property
    def latest(self) -> Optional[str]:
        return next((m.latest for m in reversed(self.metadatas) if m.latest), None)

    @property
    def versions(self) -> List[str]:
        return [v for m in self.metadatas for v in m.versions]

    @property
    def lastVersion(self) -> Optional[str]:
        return versions[-1] if (versions := self.versions) else None

    @property
    def release(self) -> Optional[str]:
        return next((m.release for m in reversed(self.metadatas) if m.release), None)


GACT = Tuple[str, str, str, str]


class Model:
    """
    A minimal Maven metadata model, tracking only dependencies and properties.
    """

    def __init__(self, env: Environment, pom: "POM"):
        """
        Builds a Maven metadata model from the given POM.

        :param pom: A source POM from which to extract metadata (e.g. dependencies).
        """
        self.env = env

        # Transfer raw metadata from POM source to target model.
        # For now, we handle only dependencies, dependencyManagement, and properties.
        self.deps: Dict[GACT, Dependency] = {}
        self.dep_mgmt: Dict[GACT, Dependency] = {}
        self.props: Dict[str, str] = {}
        self._merge(pom)

        # The following steps are adapted from the maven-model-builder:
        # https://maven.apache.org/ref/3.3.9/maven-model-builder/

        # -- profile activation and injection --

        # Compute active profiles.
        active_profiles = [
            profile
            for profile in pom.elements("profiles/profile")
            if Model._is_active_profile(profile)
        ]

        # Merge values from the active profiles into the model.
        for profile in active_profiles:
            profile_dep_els = profile.findall("dependencies/dependency")
            profile_deps = [self.env.dependency(el) for el in profile_dep_els]
            self._merge_deps(profile_deps)

            profile_dep_mgmt_els = profile.findall("dependencyManagement/dependencies/dependency")
            profile_dep_mgmt = [self.env.dependency(el) for el in profile_dep_mgmt_els]
            self._merge_deps(profile_dep_mgmt, managed=True)

            profile_props_els = profile.findall("properties")
            profile_props = {el.tag: el.text for el in profile_props_els}
            self._merge_props(profile_props)

        # -- parent resolution and inheritance assembly --

        # Merge values up the parent chain into the current model.
        parent = pom.parent
        while parent:
            self._merge(parent)
            parent = parent.parent

        # -- model interpolation --

        # Replace ${...} expressions in property values.
        for k in self.props: Model._propvalue(k, self.props)

        # Replace ${...} expressions in dependency version values.
        for dep in list(self.deps.values()) + list(self.dep_mgmt.values()):
            v = dep.version
            if v is None: continue
            dep.set_version(Model._evaluate(v, self.props))

        # -- dependency management import --

        # NB: BOM-type dependencies imported in the <dependencyManagement> section are
        # fully interpolated before merging their dependencyManagement into this model,
        # without any consideration for differing property values set in this POM's
        # inheritance chain. Therefore, unlike with parent POMs, dependency versions
        # defined indirectly via version properties cannot be overridden by setting
        # those version properties in the consuming POM!
        for k, dep in self.dep_mgmt:
            if dep.scope != "import" and dep.type == "pom": continue

            # Load the POM to import.
            bom_project = self.env.project(dep.groupId, dep.artifactId)
            bom_pom = bom_project.at_version(dep.version).pom()

            # Fully build the BOM's model, agnostic of this one.
            bom_model = Model(env, bom_pom)

            # Merge the BOM model's <dependencyManagement> into this model.
            self._merge_deps(bom_model.dep_mgmt.values(), managed=True)

        # -- dependency management injection --

        # Handles injection of dependency management into the model.
        for gacp, dep in self.deps:
            if dep.version is not None: continue
            # This dependency's version is still unset; use managed version.
            version = self.dep_mgmt.get(gacp, None)
            if version is None:
                raise ValueError("No version available for dependency {dep}")
            dep.set_version(version)

    def _merge_deps(self, source: Iterable[Dependency], managed: bool = False) -> None:
        target = self.dep_mgmt if managed else self.deps
        for dep in source:
            k = (dep.groupId, dep.artifactId, dep.classifier, dep.type)
            if k not in target: target[k] = dep

    def _merge_props(self, source: Dict[str, str]) -> None:
        for k, v in source.items():
            if k not in self.props: self.props[k] = v

    def _merge(self, pom: POM) -> None:
        """
        Transfer metadata from POM source to target model.
        For now, we handle only dependencies, dependencyManagement, and properties.
        """
        self._merge_deps(pom.dependencies())
        self._merge_deps(pom.dependencies(managed=True), managed=True)
        self._merge_props(pom.properties)

    @staticmethod
    def _is_active_profile(el):
        activation = el.find("activation")
        if activation is None: return False

        for condition in activation:
            if condition.tag == "activeByDefault":
                if condition.text == "true": return True

            elif condition.tag == "jdk":
                # TODO: Tricky...
                pass

            elif condition.tag == "os":
                # <name>Windows XP</name>
                # <family>Windows</family>
                # <arch>x86</arch>
                # <version>5.1.2600</version>
                # TODO: The db.xml generator would benefit from being able to glean
                # platform-specific dependencies. We can support it in the SimpleResolver
                # by inventing our own `platforms` field in the Dependency class and
                # changing this method to return a list of platforms rather than True.
                # But the SysCallResolver won't be able to populate it naively.
                pass

            elif condition.tag == "property":
                # <name>sparrow-type</name>
                # <value>African</value>
                pass

            elif condition.tag == "file":
                # <file>
                # <exists>${basedir}/file2.properties</exists>
                # <missing>${basedir}/file1.properties</missing>
                pass

        return False

    @staticmethod
    def _evaluate(
            expression: str,
            props: Dict[str, str],
            visited: Optional[Set[str]] = None
    ) -> str:
        props_referenced = set(findall("\\${([^}]*)}", expression))
        if not props_referenced: return expression

        value = expression
        for prop_reference in props_referenced:
            replacement = Model._propvalue(prop_reference, props, visited)
            if replacement is None:
                # NB: Leave "${...}" expressions alone when property is absent.
                # This matches Maven behavior, but it still makes me nervous.
                continue
            value = value.replace("${" + prop_reference + "}", replacement)
        return value

    @staticmethod
    def _propvalue(
            propname: str,
            props: Dict[str, str],
            visited: Optional[Set[str]] = None
    ) -> Optional[str]:
        if visited is None: visited = set()
        if propname in visited:
            raise ValueError("Infinite reference loop for property '{propname}'")
        visited.add(propname)

        expression = props.get(propname, None)
        if expression is None: return None
        evaluated = Model._evaluate(expression, props, visited)
        props[propname] = evaluated
        return evaluated
