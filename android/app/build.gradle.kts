import org.jetbrains.kotlin.gradle.dsl.JvmTarget
plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "de.peisenh.loopcrreview"
    compileSdk = 36

    defaultConfig {
        applicationId = "de.peisenh.loopcrreview"
        minSdk = 24
        targetSdk = 36
        versionCode = 7
        versionName = (findProperty("appVersion") as String?) ?: "dev"
        ndk {
            // arm64 only. numpy has to be 16 KB aligned to load on
            // current devices, and that alignment is a toolchain default for arm64
            // and nothing else — every attempt to get an aligned x86_64 wheel
            // failed, see poc/android-x86_64-16k/. Shipping an x86_64 slice that
            // cannot load its own libraries would be worse than not shipping one.
            // The emulator runs arm64 translated; -Pabi= still overrides this.
            val abi = findProperty("abi") as String?
            if (!abi.isNullOrBlank()) {
                abiFilters += abi.split(',').map { it.trim() }.filter { it.isNotEmpty() }
            } else {
                abiFilters += listOf("arm64-v8a")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlin {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }
    val keystorePath = System.getenv("ANDROID_KEYSTORE")
        ?: rootProject.file("release.jks").takeIf { it.isFile }?.absolutePath
    if (!keystorePath.isNullOrBlank()) {
        signingConfigs.create("release") {
            storeFile = file(keystorePath)
            storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                ?: error("ANDROID_KEYSTORE_PASSWORD is not set")
            keyAlias = System.getenv("ANDROID_KEY_ALIAS")?.takeIf { it.isNotBlank() } ?: "loopcr"
            keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
                ?: storePassword
        }
    }

    buildTypes {
        getByName("debug") {
            isMinifyEnabled = false
        }
        getByName("release") {
            isMinifyEnabled = false
            isDebuggable = false
            if (signingConfigs.findByName("release") != null) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
}

// The analysis is not copied into this project: it is taken from the repository
// at build time. The first version of this proof of concept carried a snapshot
// that was already several releases behind, and nothing would ever have pulled
// it forward - two truths, one of them silently wrong.
val repoRoot = rootProject.projectDir.resolve("..").canonicalFile
val pythonDir = layout.projectDirectory.dir("src/main/python")

val syncAnalysis = tasks.register<Copy>("syncAnalysis") {
    description = "Copy the current analysis from the repository into the app"
    group = "build"
    into(pythonDir)
    from(repoRoot) {
        include("loop_cr_review.py", "_version.py", "webapp.py")
    }
    from(repoRoot.resolve("lcr")) { into("lcr") }
    from(repoRoot.resolve("templates")) { into("templates") }
    from(repoRoot.resolve("static")) { into("static"); include("*.svg") }
    // Only the compiled catalogues are needed at runtime.
    from(repoRoot.resolve("locale")) { into("locale"); include("**/*.mo") }
    exclude("**/__pycache__/**")
    doFirst {
        require(repoRoot.resolve("loop_cr_review.py").exists()) {
            "repository not found at $repoRoot — expected loop_cr_review.py next to android/"
        }
    }
}

// preBuild alone is not enough: Chaquopy's own tasks read src/main/python, and
// Gradle refuses a task that consumes another task's output without the
// dependency being declared ("A problem was found with the configuration of
// task ':app:mergeDebugPythonSources'"). Naming them explicitly settles the
// order instead of leaving it to chance.
tasks.named("preBuild") { dependsOn(syncAnalysis) }
tasks.matching { it.name.matches(Regex("(merge|generate|extract).*Python.*")) }
    .configureEach { dependsOn(syncAnalysis) }

val wheelsDir = layout.projectDirectory.dir("wheels").asFile

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            // numpy 2.3.2 from pypi-upstream, which is 16 KB aligned for arm64.
            // It is the only compiled dependency left: the charts are drawn as
            // SVG now, so there is no matplotlib and no hand-built wheel.
            //
            // find-links stays: fetch-android-wheels.sh puts the wheel in
            // app/wheels/, and without this pip ignores it and downloads its
            // own copy — the fetch step would be doing nothing.
            options("--extra-index-url", "https://chaquo.com/pypi-upstream")
            options("--find-links", wheelsDir.absolutePath)
            install("numpy==2.3.2")

            install("Flask==3.1.2")
            install("Jinja2==3.1.6")
            install("waitress==3.0.2")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    // No AppCompat: the activity is a WebView container and uses a plain
    // platform theme. Pulling it in would only add size and the requirement
    // to inherit from Theme.AppCompat.
}
