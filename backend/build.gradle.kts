plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.launchpilot"
version = "0.1.0"

java {
    toolchain {
        // C4 명시: Java 21. 미설치 시 Gradle이 foojay로 자동 프로비저닝.
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    // 계약 01/02 asyncapi: FE-facing WS 서버 + Python-facing WS 클라이언트
    implementation("org.springframework.boot:spring-boot-starter-websocket")

    // Elastic Cloud Serverless: 공식 Java Client (계약 03)
    implementation("co.elastic.clients:elasticsearch-java:8.15.3")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    // Python 인프라(계약 02) 스텁
    testImplementation("org.wiremock:wiremock-standalone:3.9.2")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
