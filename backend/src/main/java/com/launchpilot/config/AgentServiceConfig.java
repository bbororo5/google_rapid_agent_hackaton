package com.launchpilot.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

/** Python 인프라(계약 02) 호출용 RestClient. base URL = AGENT_SERVICE_URL. */
@Configuration
public class AgentServiceConfig {

    /**
     * Create a RestClient configured to communicate with the Agent service.
     *
     * @param builder a RestClient.Builder used to construct the client
     * @param baseUrl the Agent service base URL (injected from the `agent.service.url` property)
     * @return a RestClient whose base URL is set to the provided `baseUrl`
     */
    @Bean
    public RestClient agentRestClient(
            RestClient.Builder builder,
            @Value("${agent.service.url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
