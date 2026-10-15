plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// SCF 函数 URL：编译期注入，见 SRS_app.md §9（做法 A：仅编译期配置）
val scfBaseUrl: String = (project.findProperty("SCF_BASE_URL") as String?)
    ?: "https://1480388537-j4cnl3240r.ap-guangzhou.tencentscf.com"

android {
    namespace = "com.example.stockkline"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.stockkline"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        buildConfigField("String", "SCF_BASE_URL", "\"$scfBaseUrl\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
        viewBinding = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
