pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "PocketBot"
include(":app")
// Núcleo sin dependencias de Android (estrategia, backtest, protocolo).
// Se puede probar por separado: gradle -p core test
includeBuild("core")
