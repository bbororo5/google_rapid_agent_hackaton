package com.launchpilot.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

/** Python 인프라(계약 02) 호출용 RestClient. base URL = AGENT_SERVICE_URL. */
@Configuration
public class AgentServiceConfig {

    @Bean
    public RestClient agentRestClient(
            RestClient.Builder builder,
            @Value("${agent.service.url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
