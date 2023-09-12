## Maven-based ImageJ update site generator

*I.e.: a tool for converting from `pom.xml` files to `db.xml.gz` files.*

## Status/disclaimer

**This work is currently a PROTOTYPE.** It is close to fully functional, but still has a couple of missing pieces. The plan is to finish this work during the month of September 2023, at which point this repository will disappear in favor of its two halves being parceled out to appropriate destinations: the general Maven part to [jgo](https://github.com/scijava/jgo), and the ImageJ update site generation part to somewhere in the [imagej org](https://github.com/imagej), likely either the [imagej-updater](https://github.com/imagej) component or a new repository.

## Overview

This pom.xml-to-db.xml generator has two parts: `maven.py` and `updater.py`.

### maven.py

The `maven.py` portion has nothing to do with ImageJ2, it's just a pure-Python implementation of Maven dependency reasoning. So you can e.g. list dependencies of a Maven component (G:A:V), including transitive dependencies, using the same algorithm that maven-core uses when you run e.g. `mvn dependency:list` or `mvn dependency:tree`.

Example CLI invocation for project metadata:

```python
$ python maven.py org.scijava:scijava-common:2.96.0
[org.scijava:scijava-common:2.96.0]
org.scijava:parsington:jar:3.1.0:compile
junit:junit:jar:4.13.2:test
org.mockito:mockito-core:jar:2.19.0:test
org.hamcrest:hamcrest-core:jar:1.3:test
net.bytebuddy:byte-buddy:jar:1.8.10:test
net.bytebuddy:byte-buddy-agent:jar:1.8.10:test
org.objenesis:objenesis:jar:3.3:test
```

The `maven.py` library also understands `maven-metadata.xml`, and can report statistics about a project (G:A):

Example CLI invocation for component details:

```python
$ python maven.py org.scijava:scijava-common
[org.scijava:scijava-common]
groupId = org.scijava
artifactId = scijava-common
lastUpdated = 2023-08-03 14:50:58
latest = None
lastVersion = 2.95.0-SNAPSHOT
release = None
release version count = 0
snapshot version count = 1
```

As you can see from the above output, the metadata is wrong. This is due to the fact that currently, the library just reads `maven-metadata.xml` files from local sources such as the repo cache (`~/.m2/repository/org/scijava/scijava-common/maven-metadata*.xml`), but does not proactively update these metadata sources from remotes yet. Adding this will be easy, though.

The `maven.py` API for working with Maven projects is fleshed out and 95+% functional.

Example Python program using the `maven.py` library:

```python
from maven import Environment, Model

env = Environment()

g = "org.scijava"
a = "scijava-common"
v = "2.96.0"

# Print information about this project (G:A).
project = env.project(g, a)
print(f"Metadata for {project}:")
metadata = project.metadata
for field in (
    "groupId", "artifactId", "lastUpdated",
    "latest", "lastVersion", "release"
):
    print(f"{field} = {getattr(metadata, field)}")
snapshot_count = sum(1 for v in metadata.versions if v.endswith("-SNAPSHOT"))
release_count = len(metadata.versions) - snapshot_count
print(f"release version count = {release_count}")
print(f"snapshot version count = {snapshot_count}")

# Print dependencies of this component (G:A:V).
component = env.project(g, a).at_version(v)
print()
print(f"Dependencies for {component}:")
model = Model(component.pom())
for dep in model.dependencies():
    print(dep)
```

which prints:

```
Metadata for org.scijava:scijava-common:
groupId = org.scijava
artifactId = scijava-common
lastUpdated = 2023-07-27 13:45:27
latest = None
lastVersion = 2.95.0-SNAPSHOT
release = None
release version count = 0
snapshot version count = 2

Dependencies for org.scijava:scijava-common:2.96.0:
org.scijava:parsington:jar:3.1.0:compile
junit:junit:jar:4.13.2:test
org.mockito:mockito-core:jar:2.19.0:test
org.hamcrest:hamcrest-core:jar:1.3:test
net.bytebuddy:byte-buddy:jar:1.8.10:test
net.bytebuddy:byte-buddy-agent:jar:1.8.10:test
org.objenesis:objenesis:jar:3.3:test
```

#### Benefits

The existence of this pure-Python `maven.py` library brings some major benefits:

1. Of course, it is foundational to the `db.xml.gz` generator (see `updater.py` section below).

2. The plan is to migrate the `maven.py` code into [jgo](https://github.com/scijava/jgo), replacing jgo's current logic that shells out to the `mvn` command line tool. In this way, jgo will shed its `maven` conda dependency, and using jgo only to build environments will not even require `openjdk`; you will only need Java installed if you want to *launch* the main entry point of an environment.

3. It will allow us to finish improving the website https://status.scijava.org/, which needs to extract metadata about all the Maven projects listed in that big table. Right now, there is largely working code on the [github-issues branch](https://github.com/scijava/status.scijava.org/compare/github-issues) which revamps the status.scijava.org website, and contains an older/lesser version of this `maven.py` library, along with an older/lesser version of the `github.py` library that exists as part of my [monoqueue](https://github.com/ctrueden/monoqueue) project. My plan is to finish that `github-pages` branch by making it depend on the latest and greatest `jgo` and `monoqueue` projects, i.e. reuse code rather than copy/pasting it.

4. It will facilitate us finishing the revamp of https://javadoc.scijava.org/ infrastructure, currently quite far along in the [javadoc-wrangler](https://github.com/scijava/javadoc-wrangler) repository. If you look in `wrangle.py` there you will see yet another older/lesser version of this `maven.py` library, which we can now excise in favor of depending on a new `jgo` there as well.

### updater.py

The second half of this repository is `updater.py`, the code that leans on `maven.py` to generate `db.xml` content.

```python
$ python updater.py org.scijava:scijava-common
Creating Maven environment...
Initializing FilesCollection...
Processing org.scijava:scijava-common...
Adding artifact org.scijava:scijava-common:jar:2.96.0...
Registered org.scijava:scijava-common:jar:2.96.0 <-- CURRENT
Registered org.scijava:parsington:jar:3.1.0 <-- CURRENT
Registered org.scijava:scijava-common:jar:1.0.0
Registered net.java.sezpoz:sezpoz:jar:1.9
Registered org.bushe:eventbus:jar:1.4
Registered org.scijava:scijava-common:jar:1.1.0
Registered org.scijava:scijava-common:jar:1.2.0
...
Registered org.scijava:scijava-common:jar:2.94.1
Registered org.scijava:scijava-common:jar:2.94.2
Registered org.scijava:scijava-common:jar:2.95.0
Registered org.scijava:scijava-common:jar:2.95.1
Generating resultant XML...
$ ll db-*
-rw-rw-r-- 1 curtis curtis 33K Aug 18 12:48 db-org.scijava-scijava-common-2.96.0.xml
```

As you can infer from the above output, the `updater.py` builds up dependency metadata for *all* available versions of the given project (in this case `org.scijava:scijava-common`), and generates a `db.xml` file with `<plugin>` entries encompassing all such versions and all of their dependencies. In this way, any ImageJ installation at any previous state will be cleanly upgradeable to whatever the current versions of artifacts are declared to be.

Here is an excerpt of the XML currently generated by the above invocation:
```xml
<plugin filename="scijava-common-2.96.0.jar">
<version checksum="8dee3846e4ca1a0ad4169cf5e4859bcf52b878af" timestamp="20230806155713" filesize="948993">
  <description>SciJava Common is a shared library for SciJava software. It provides a plugin framework, with an extensible mechanism for service discovery, backed by its own annotation processor, so that plugins can be loaded dynamically. It is used by downstream projects in the SciJava ecosystem, such as ImageJ and SCIFIO.</description>
  <dependency filename="jars/parsington-3.1.0.jar" timestamp="20230803093430"/>
  <dependency filename="jars/junit-4.13.2.jar" timestamp="20211023192336"/>
  <dependency filename="jars/mockito-core-2.19.0.jar" timestamp="20211116195400"/>
  <dependency filename="jars/hamcrest-core-1.3.jar" timestamp="20211012150405"/>
  <dependency filename="jars/byte-buddy-1.8.10.jar" timestamp="20211116195400"/>
  <dependency filename="jars/byte-buddy-agent-1.8.10.jar" timestamp="20211116195400"/>
  <dependency filename="jars/objenesis-3.3.jar" timestamp="20230803093430"/>
  ...
</version>
<previous-version timestamp="20230816143228" checksum="8dee3846e4ca1a0ad4169cf5e4859bcf52b878af" filename="jars/scijava-common-2.17.0.jar"/>
...
<previous-version timestamp="20151231043333" checksum="8dee3846e4ca1a0ad4169cf5e4859bcf52b878af" filename="jars/scijava-common-2.50.0.jar"/>
</plugin>
<plugin filename="gentyref-1.1.0.jar">
<previous-version timestamp="20100607164719" checksum="8dee3846e4ca1a0ad4169cf5e4859bcf52b878af" filename="jars/gentyref-1.1.0.jar"/>
</plugin>
<plugin filename="parsington-3.1.0.jar">
<version checksum="8dee3846e4ca1a0ad4169cf5e4859bcf52b878af" timestamp="20230803093430" filesize="47987">
  <description>A general-purpose mathematical expression parser, which converts infix expression strings into postfix queues and/or syntax trees.</description>
  <dependency filename="jars/junit-jupiter-api-5.9.1.jar" timestamp="20220920133431"/>
  <dependency filename="jars/junit-jupiter-engine-5.9.1.jar" timestamp="20220920133430"/>
  <dependency filename="jars/opentest4j-1.2.0.jar" timestamp="20211116195359"/>
  <dependency filename="jars/junit-platform-commons-1.9.1.jar" timestamp="20220920133430"/>
  <dependency filename="jars/apiguardian-api-1.1.2.jar" timestamp="20220926123313"/>
  <dependency filename="jars/junit-platform-engine-1.9.1.jar" timestamp="20220920133434"/>
  ...
</version>
<previous-version timestamp="20211012153514" checksum="8dee3846e4ca1a0ad4169cf5e4859bcf52b878af" filename="jars/parsington-1.0.1.jar"/>
...
</plugin>
```

A few things to notice here:

1. By and large, the generator is populating all the right information from the POM sources. Woot!

2. If you think about how this must work, the tool needs to resolve every POM and JAR file backward throughout history for that Maven project, which for `net.imagej:imagej` and `sc.fiji:fiji` is a whole lot of files! I'm not sure exactly how many yet, but it's on the order of 2<sup>10</sup> artifacts times 2<sup>4</sup> versions each times 2 (POM and JAR) ~= 2<sup>15</sup> ~= 32K files to download and cache into a `~/.m2/repository` cache. Assuming each JAR files averages 128KB or more, that's at least multiple GB, if not dozens of GB, in total size.

   To avoid these concerns, the backing `maven.py` library supports *discovery of Maven artifacts directly from a Nexus 2 directory structure*, so that the `updater.py` generator can be executed on the maven.scijava.org server, and run blazingly fast without needing to make any/many remote HTTPS requests. This feature is already testing and working!

3. The generator does not bother with `timestamp-obsolete` fields, because this mechanism obviates the need for them. That field was originally added aspirationally with the idea that it could facilitate a future "downgrade" feature for the Updater. But that feature was never coded, and now, we can instead handle downgrading a different way: by generating a *different update site* for each version of a Maven project. For example, https://sites.imagej.net/org.scijava/scijava-common/db-2.94.2.xml.gz, https://sites.imagej.net/org.scijava/scijava-common/db-2.96.0.xml.gz, etc., one `db.xml` file per version of scijava-common. The Updater could then be easily enhanced to switch the update site target for scijava-common to whichever version the user selects from a dropdown box. And https://sites.imagej.net/org.scijava/scijava-common/latest/ can be a rolling symlink to whatever version the maintainers want to be used with the "latest and greatest" ImageJ2, Fiji, etc.

4. A consequence of this upgrade/downgrade scheme is that every `db.xml` should include *all versions* of all files, with the *current* version being the desired one. In this way, downgrading from newer versions "just works" without showing any files as "locally modified." But then every time a new project version is released, *all* `db.xml`s must be updated to include it. So it is critical that we get this automation right, so that no manual tweaking is necessary as the number of releases grows for each project.

5. The checksum fields are currently wrong: just a hardcoded placeholder. This is because the ImageJ Updater's checksum is a "smart" (and therefore more nuanced to compute) checksum based on the actual contents of the JAR file, rather than the file in total. So even though Maven records MD5 and SHA1 checksums for every artifact, we cannot use these here, and instead will need to compute Updater-style checksums, either in Python or by leaning on the existing Java Updater code. I have not yet investigated doing this, but am confident it can be done in an extensible way. It's just one more piece of work to do for this project.

6. There is currently a significant bug/limitation in `maven.py` when properties are used for dependency fields other than `<version>`. For example, some projects will use `<groupId>${project.version}</groupId>` when depending on other components of the same software suite, such as miglayout-swing depending on miglayout-core. The `maven.py` property interpolator currently only evalutes such property expressions in the `<version>` field, not the `<groupId>`, `<artifactId>`, or `<classifier>` fields. You might think it would be straightforward to do so, but the `maven.py` model builder relies on using GACT (groupId/artifactId/classifier/type) tuples as keys in its dependency dicts, because you don't want to include more than one version of the same GACT in the dependency list. But when `${...}` expressions get evaluated in the G/A/C/T fields, it will *change that key value*, which complicates management of those dicts. A) What if we interpolate some such expressions and then there is a new key clash in the dicts? What should we do? B) What if there is a key clash around a G value of `${project.groupId}` which will later evaporate after interpolation? How can we avoid erroneously stomping actually-not-the-same dependencies that temporarily overlap due to identical such expressions? How does maven-core even deal with this? Does it have bugs around such edge cases? Or does it have some hacky logic to avoid these issues? I haven't read the code yet to find out...

7. There is some scaffolding in place for OS/arch-specific activation of Maven profiles. But more thought is needed around exactly how to manage this. The typical use case for these is to have OS/arch-specific dependencies, particularly native classifier JARs. It would be nice if the db.xml generation did so for *all* supported platforms, by simulating each active platform when activating profiles, and including such contingent dependencies with the proper `<platform>` declaration in the db.xml. This is doable, but a little tricky to get exactly right for all cases we need to support.

## What's left to do?

### Remaining tasks for this codebase

Hopefully the writeup above makes it clear that this project is close to being usable in production for our community. But there are still things left to do before it can really start being tested against real-world use cases.

1. Compute and populate the checksums correctly (point 5 of `updater.py` above).

2. Fix the bug with test-scoped dependencies being erroneously included (point 6 of `updater.py` above).

3. Fix the bug with dependency property interpolation (point 6 of `updater.py` above).

4. Implement the platform-specific profiles support (point 7 of `updater.py` above).

5. Do more manual generation attempts for `net.imagej:imagej` and `sc.fiji:fiji` (since these two projects will be the eventual inputs for this scheme), fixing any other problems discovered during testing, beyond those already outlined above.

6. Enhance the `updater.py` to generate not only *one* update site for a given version of a project, but rather *all* update sites, one per version (points 3 and 4 above).

7. Add a way to supplement known versions of each particular project artifact with all non-Maven versions that have historically shipped on core update sites. This is necessary because over the years, many people have built their own local JAR binaries and uploaded them directly, rather than just uploading the official CI builds that were deployed to remote Maven repositories. Fortunately, I think solving this might be as simple as pasting all such historical `previous-versions` into the `template.xml` that contains the scaffolding/boilerplate for update sites in general. Probably only small tweaks needed to `updater.py` to reuse an existing `<plugin>` entry when it's already present from the template itself.

8. Consider whether to support "unstable" update sites by tracking SNAPSHOT versions built by CI from latest mainline branches. Support for stable vs unstable update sites has been requested by power users and devs for a long time, and this work could be a good opportunity to deliver on it.

### Tasks in the ImageJ Updater

Once the Maven-to-`db.xml` generator is robust enough, we then need to enhance the ImageJ Updater to take advantage of it:

1. As described above, the Maven-driven generator will make *one db.xml.gz per release version*.

2. To support smoother upgrading of major Java versions over time, the `db.xml` schema must gain a new "minimum Java version" field, which will enable the Updater to know, for every version of a project/site, what version of Java is needed in order to use it. The Maven-to-`db.xml` generator can be enhanced quite easily to embed this minimum Java version into the `db.xml` files it generates.

3. The Updater needs to check the currently running version of Java, and refuse to update if it is older than the needed minimum for the currently enabled update sites.

4. When a particular project updates to a new major Java version, symlinks can be used to keep track of which versions correspond to which major Java versions. For example, suppose that we now were to release scijava-common at 3.0.0 and require Java 11, making 2.96.0 the last version to support Java 8. The update site `/org.scijava/scijava-common/3.0.0/db.xml.gz` would document Java 11 as minimum, while `/org.scijava/scijava-common/2.96.0/db.xml.gz` would document Java 8 as minimum. The update sites `/org.scijava/scijava-common/latest` and `/org.scijava/scijava-common/latest11` would symlink to `3.0.0`, while the update site `/org.scijava/scijava-common/latest8` would symlink to `2.96.0`. The Updater could then be taught to understand these conventions, and automatically use the right `latest<X>` site for the current major version of Java. In this way, the generic `/latest` symlink might not even be necessary, only the Java-versioned `/latest<X>` links.

5. Make the imagej-updater stand alone with no dependencies. In this way, we can have a truly core *Updater* update site (maybe even have the "update the updater" mechanic work specially, outside of the update site infrastructure?) shipping only the latest Java-6-based ImageJ Updater and nothing else, which is common to all ImageJ2 installations. The current imagej-updater only lightly depends on scijava-common (in particular for the uploader plugins, which pragmatically don't actually need to be plugins), so this task is worth doing because it's low effort and avoids the difficult maintenance headache of scijava-common updates breaking ImageJ2 installations by breaking the Updater. We could make the ImageJ Launcher fall back to an graphical installation repair tool in cases where the SciJava Context creation barfs, eliminating this historical source of pain from our user community. In a nutshell: this design gives us the ability to fix bugs in the Updater independently of everything else, which is sorely needed.

6. We could split out the original ImageJ's `ij.jar` into its own `ImageJ` update site, so that one can have a barebones ImageJ installation without parts of ImageJ2 beyond only the ImageJ Updater. The Launcher would just need to be smart enough to notice that only ImageJ, not ImageJ2, is currently installed, and start up the application appropriately.

7. Relatedly: after tackling the previous two points above, we could probably drop the hard imagej-updater dependency from net.imagej:imagej, instead making it optional.

8. Consider teaching the Updater to understand MD5 and/or SHA1 checksums, in addition to its current checksum format. This might simplify generation of update sites. But further investigation needed before deciding. For example: consider how this feature would behave if upgrading from a pre-2023 installation to a post-2023 one.

9. Less urgently, hopefully some time in 2024: teach the Updater how to offer "downgrades" using these spiffy new versioned update sites.

### Other tasks

We should grow the existing `template.xml` to include all versions currently in https://sites.imagej.net/Java-8/db.xml.gz. It's a big chunk of XML, but size of these `db.xml` files is still tiny compared to the binaries, and it will allow the Updater to easily do awesome things like "convert my Fiji installation into a basic ImageJ2 one" without hassle. I.e. we will get the future split of ImageJ2 core "for free" via generation of `net.imagej:imagej` sites on top of the big honkin' template filled with these historical version hashes.

## Parting thoughts

After reading all of the above, you might be thinking: "Gosh, all of this is so complicated! Wouldn't it be easier to just use, e.g., git for versioning and updates? Or adapt some existing Java library that handles it for us?" I just want to ask you to push back on such thoughts: please realize that the above goes into a lot of detail because this scheme will *actually work* while preserving full backwards compatibility, and solve all of our requirements such as upgrading major Java versions cleanly, among many other concerns. The above is really an exhaustive list of all the issues that have occurred to me so far, rather than only vague hand-waving. Whereas on the flip side: while developers in our community have attempted to redesign the ImageJ Updater mechanism wholesale in the past&mdash;and it's relatively easy to get simple proof-of-concept code working e.g. backed by git&mdash;there are many remaining issues with those approaches that were not solved and are potentially hard to solve. I firmly believe that there is no simpler "silver bullet" solution that would obviate the need to do any of the above work. On the contrary: I think the above work is quite minimal compared to any other proposed more radical approach, any of which would have much more substantial wrinkles, difficulties, unintended consequences, etc.

Anyway, thank you so much for reading this far! :cookie:
