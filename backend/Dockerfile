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
COPY --from=build /src/build/libs/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
