plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

android {
    namespace = "com.example.loopcr"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.example.loopcr"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0-poc"
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildTypes {
        getByName("debug") {
            isMinifyEnabled = false
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
val repoRoot = rootProject.projectDir.resolve("../..").canonicalFile
val pythonDir = layout.projectDirectory.dir("src/main/python")

val syncAnalysis by tasks.registering(Copy::class) {
    description = "Copy the current analysis from the repository into the app"
    group = "build"
    into(pythonDir)
    from(repoRoot) {
        include("loop_cr_review.py", "_version.py", "webapp.py")
    }
    from(repoRoot.resolve("lcr")) { into("lcr") }
    from(repoRoot.resolve("templates")) { into("templates") }
    // Only the compiled catalogues are needed at runtime.
    from(repoRoot.resolve("locale")) { into("locale"); include("**/*.mo") }
    exclude("**/__pycache__/**")
    doFirst {
        require(repoRoot.resolve("loop_cr_review.py").exists()) {
            "repository not found at $repoRoot - this project expects to sit in poc/ inside it"
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

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            // Chaquopy's own index (pypi-13.1) has numpy 1.26.2 at the newest,
            // and that wheel's libgfortran will not load on a 16 KB page size
            // device. chaquo.com/pypi-upstream carries numpy 2.3.2 for both ABIs,
            // built December 2025 - late enough to be 16 KB aligned. That index
            // is not searched by default, so it is added here.
            //
            // If this turns out not to resolve, drop the two lines below and the
            // pin: the build then falls back to 1.26.2, which works on a 4 KB
            // device. The analysis itself runs on either - the test suite passes
            // with numpy 1.26 and matplotlib 3.8, and the report comes out
            // text-identical to the one built with numpy 2.x.
            options("--extra-index-url", "https://chaquo.com/pypi-upstream")
            install("numpy==2.3.2")

            // Left unpinned on purpose: it has to be a build that matches
            // numpy 2.x. matplotlib 3.8 was compiled against numpy 1 and may
            // fail at import with an ABI complaint even though it installs -
            // watch the build log for which version is picked.
            install("matplotlib")

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
