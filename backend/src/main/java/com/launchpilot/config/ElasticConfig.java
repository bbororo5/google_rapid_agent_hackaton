package com.launchpilot.config;

import co.elastic.clients.json.JsonpMapper;
import co.elastic.clients.json.jackson.JacksonJsonpMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.http.Header;
import org.apache.http.message.BasicHeader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.elasticsearch.RestClientBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

/**
 * Elastic Cloud Serverless (계약 03).
 * RestClient/Transport/ElasticsearchClient는 Spring Boot 자동설정이 생성
 * (spring.elasticsearch.uris). 여기서는 두 가지만 주입:
 * - API Key 인증 헤더 (RestClientBuilderCustomizer)
 * - snake_case JsonpMapper (계약 필드명대로 문서 직렬화)
 */
@Configuration
public class ElasticConfig {

    /** ES 문서를 계약대로 snake_case 직렬화. 자동설정 기본 매퍼 대신 사용. */
    @Bean
    public JsonpMapper jsonpMapper(ObjectMapper objectMapper) {
        return new JacksonJsonpMapper(objectMapper);
    }

    /** Serverless API Key 인증: Authorization: ApiKey <key>. */
    @Bean
    public RestClientBuilderCustomizer apiKeyCustomizer(
            @Value("${elastic.api-key:}") String apiKey) {
        return builder -> {
            if (StringUtils.hasText(apiKey)) {
                builder.setDefaultHeaders(new Header[] {
                        new BasicHeader("Authorization", "ApiKey " + apiKey)
                });
            }
        };
    }
}
