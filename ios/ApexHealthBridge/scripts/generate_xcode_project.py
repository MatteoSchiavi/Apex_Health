#!/usr/bin/env python3
"""Generate the committed Xcode project without XcodeGen, CocoaPods, or network access."""
import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def identifier(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()


def quoted(value):
    return json.dumps(str(value))


def generate(bundle_id, team):
    objects = {}

    def add(name, body):
        uid = identifier(name)
        objects[uid] = body
        return uid

    source_refs, builds = [], []
    for path in sorted((ROOT / "Sources").rglob("*.swift")):
        relative = path.relative_to(ROOT).as_posix()
        ref = add("ref:" + relative, f'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = {quoted(relative)}; sourceTree = "<group>";')
        source_refs.append(ref)
        builds.append(add("build:" + relative, f"isa = PBXBuildFile; fileRef = {ref};"))
    privacy = add("privacy", 'isa = PBXFileReference; lastKnownFileType = text.xml; path = PrivacyInfo.xcprivacy; sourceTree = "<group>";')
    privacy_build = add("privacy-build", f"isa = PBXBuildFile; fileRef = {privacy};")
    resources = add("resources", f"isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = ({privacy_build},); runOnlyForDeploymentPostprocessing = 0;")
    product = add("product", 'isa = PBXFileReference; explicitFileType = wrapper.application; path = ApexHealthBridge.app; sourceTree = BUILT_PRODUCTS_DIR;')
    products = add("products", f'isa = PBXGroup; children = ({product},); name = Products; sourceTree = "<group>";')
    group = add("group", 'isa = PBXGroup; children = (' + ','.join(source_refs + [privacy, products]) + ',); sourceTree = "<group>";')
    sources = add("sources", 'isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = (' + ','.join(builds) + ',); runOnlyForDeploymentPostprocessing = 0;')
    frameworks = add("frameworks", 'isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0;')
    app_configs, project_configs = [], []
    for mode in ["Debug", "Release"]:
        app_settings = {
            "PRODUCT_NAME": "$(TARGET_NAME)", "PRODUCT_BUNDLE_IDENTIFIER": bundle_id,
            "INFOPLIST_FILE": "Info.plist", "CODE_SIGN_ENTITLEMENTS": "ApexHealthBridge.entitlements",
            "CODE_SIGN_STYLE": "Automatic", "DEVELOPMENT_TEAM": team,
            "SWIFT_VERSION": "5.0", "SWIFT_STRICT_CONCURRENCY": "targeted",
            "IPHONEOS_DEPLOYMENT_TARGET": "17.0", "TARGETED_DEVICE_FAMILY": "1",
            "SUPPORTED_PLATFORMS": "iphoneos iphonesimulator", "SDKROOT": "iphoneos",
            "GENERATE_INFOPLIST_FILE": "NO", "ENABLE_USER_SCRIPT_SANDBOXING": "YES",
        }
        project_settings = {
            "CLANG_ENABLE_MODULES": "YES", "CLANG_ENABLE_OBJC_ARC": "YES",
            "SWIFT_OPTIMIZATION_LEVEL": "-Onone" if mode == "Debug" else "-O",
            "DEBUG_INFORMATION_FORMAT": "dwarf" if mode == "Debug" else "dwarf-with-dsym",
        }
        if mode == "Debug":
            app_settings["SWIFT_ACTIVE_COMPILATION_CONDITIONS"] = "DEBUG"
            app_settings["ENABLE_TESTABILITY"] = "YES"
        for prefix, settings, result in [("app", app_settings, app_configs), ("project", project_settings, project_configs)]:
            body = " ".join(f"{key} = {quoted(value)};" for key, value in settings.items())
            result.append(add(prefix + mode, f"isa = XCBuildConfiguration; buildSettings = {{ {body} }}; name = {mode};"))
    app_list = add("app-configs", f"isa = XCConfigurationList; buildConfigurations = ({','.join(app_configs)},); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;")
    project_list = add("project-configs", f"isa = XCConfigurationList; buildConfigurations = ({','.join(project_configs)},); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;")
    target = add("app-target", f'isa = PBXNativeTarget; buildConfigurationList = {app_list}; buildPhases = ({sources},{frameworks},{resources},); buildRules = (); dependencies = (); name = ApexHealthBridge; productName = ApexHealthBridge; productReference = {product}; productType = "com.apple.product-type.application";')
    project = add("project", f'isa = PBXProject; attributes = {{ LastUpgradeCheck = 1600; TargetAttributes = {{ {target} = {{ CreatedOnToolsVersion = 16.0; }}; }}; }}; buildConfigurationList = {project_list}; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en,Base,); mainGroup = {group}; productRefGroup = {products}; projectDirPath = ""; projectRoot = ""; targets = ({target},);')
    project_path = ROOT / "ApexHealthBridge.xcodeproj"
    project_path.mkdir(exist_ok=True)
    lines = ["// !$*UTF8*$!", "{", "archiveVersion = 1;", "classes = {};", "objectVersion = 56;", "objects = {"]
    lines += [f"{uid} = {{ {body} }};" for uid, body in objects.items()]
    lines += ["};", f"rootObject = {project};", "}"]
    (project_path / "project.pbxproj").write_text("\n".join(lines) + "\n")
    schemes = project_path / "xcshareddata" / "xcschemes"
    schemes.mkdir(parents=True, exist_ok=True)
    reference = f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="ApexHealthBridge.app" BlueprintName="ApexHealthBridge" ReferencedContainer="container:ApexHealthBridge.xcodeproj"/>'
    (schemes / "ApexHealthBridge.xcscheme").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1600" version="1.3">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{reference}</BuildActionEntry></BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables/></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugServiceExtension="internal" allowLocationSimulation="NO"><BuildableProductRunnable runnableDebuggingMode="0">{reference}</BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugServiceExtension="internal"><BuildableProductRunnable runnableDebuggingMode="0">{reference}</BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/>
<ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
''')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-id", default="org.apexhealth.bridge")
    parser.add_argument("--team", default="")
    args = parser.parse_args()
    generate(args.bundle_id, args.team)
