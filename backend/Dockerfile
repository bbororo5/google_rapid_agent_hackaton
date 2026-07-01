# Java Spring Boot backend. Build context: backend
# Stage 1: build the bootJar with the Gradle wrapper.
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY . .
# Normalize possible CRLF in gradlew (Windows checkout) so the linux shell runs it.
RUN sed -i 's/\r$//' gradlew && chmod +x gradlew && \
    ./gradlew --no-daemon clean bootJar -x test

# Stage 2: slim runtime with just the JRE + jar.
FROM eclipse-temurin:21-jre
WORKDIR /app
ARG OTEL_JAVA_AGENT_VERSION=2.20.1
ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${OTEL_JAVA_AGENT_VERSION}/opentelemetry-javaagent.jar /otel/opentelemetry-javaagent.jar
COPY --from=build /src/build/libs/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
