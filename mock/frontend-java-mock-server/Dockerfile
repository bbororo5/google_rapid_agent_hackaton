FROM gradle:8.14-jdk21-alpine AS build

WORKDIR /app
COPY settings.gradle.kts build.gradle.kts ./
COPY src ./src
RUN gradle bootJar --no-daemon

FROM eclipse-temurin:21-jre-alpine

WORKDIR /app
COPY --from=build /app/build/libs/frontend-java-mock-server-0.1.0.jar /app/frontend-java-mock-server.jar

EXPOSE 8090

ENTRYPOINT ["java", "-jar", "/app/frontend-java-mock-server.jar"]
