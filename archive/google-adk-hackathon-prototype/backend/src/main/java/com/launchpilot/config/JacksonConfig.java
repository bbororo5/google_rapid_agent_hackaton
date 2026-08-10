package com.launchpilot.config;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

/**
 * 계약 strict 직렬화:
 * - snake_case 필드명 (모든 계약 JSON).
 * - 알 수 없는 필드 거부 (additionalProperties:false 대응).
 * - null 유지 (payload:null, error_message:null 등 nullable 계약 필드 표현).
 * 이 한 개 빈을 Spring Web + Elastic 클라이언트가 공유한다.
 */
@Configuration
public class JacksonConfig {

    /**
     * Creates the primary Jackson ObjectMapper configured for the application.
     *
     * <p>The mapper uses snake_case for JSON property names and will fail deserialization
     * when unknown properties are encountered.</p>
     *
     * @return an ObjectMapper that uses snake_case naming and fails on unknown properties
     */
    @Bean
    @Primary
    public ObjectMapper objectMapper() {
        return new ObjectMapper()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }
}
