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
            // Keep in sync with desktop requirements where practical
            // NOT the versions from requirements.txt. Chaquopy builds its own
            // wheels for Android and the scientific packages lag well behind the
            // desktop ones - numpy 2.3.5 simply does not exist there, the build
            // stops with "Could not find a version that satisfies the
            // requirement". Leave numpy and matplotlib unpinned so pip takes
            // whatever Chaquopy offers, and pin the pure-Python ones.
            //
            // The analysis runs on numpy 1.26 / matplotlib 3.8 as well: the full
            // test suite passes and the generated report is text-identical to the
            // one built with numpy 2.x. Only the chart rasterisation differs.
            install("numpy")
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
