package com.launchpilot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LaunchPilotApplication {
    /**
     * Application entry point that bootstraps and starts the Spring Boot application.
     *
     * @param args command-line arguments passed to the application; may be empty
     */
    public static void main(String[] args) {
        SpringApplication.run(LaunchPilotApplication.class, args);
    }
}
