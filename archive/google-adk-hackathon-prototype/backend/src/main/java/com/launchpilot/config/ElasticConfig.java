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

    /**
     * Register a JsonpMapper bean that delegates JSON mapping to the given Jackson ObjectMapper.
     *
     * @param objectMapper the Jackson ObjectMapper to back the JsonpMapper (controls serialization settings)
     * @return a JsonpMapper backed by the provided ObjectMapper
     */
    @Bean
    public JsonpMapper jsonpMapper(ObjectMapper objectMapper) {
        return new JacksonJsonpMapper(objectMapper);
    }

    /**
     * Customize the Elasticsearch REST client to add an `Authorization: ApiKey <key>` header when an API key is provided.
     *
     * @param apiKey the API key (from `elastic.api-key`); if empty or blank no header will be added
     * @return a RestClientBuilderCustomizer that sets a default `Authorization` header with the ApiKey when `apiKey` has text
     */
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
