package com.launchpilot.api;

import com.launchpilot.dto.pub.AgentRunAcceptedResponse;
import com.launchpilot.dto.pub.AgentRunRequest;
import com.launchpilot.dto.pub.AgentRunStatusResponse;
import com.launchpilot.dto.pub.ApproveExperimentPlanRequest;
import com.launchpilot.dto.pub.ApproveExperimentPlanResponse;
import com.launchpilot.service.AgentRunService;
import com.launchpilot.service.ApiException;
import com.launchpilot.service.BusinessDataService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 계약 01: 에이전트 트리거 / 폴링 / 승인. */
@RestController
@RequestMapping("/api/agent")
public class AgentController {

    private static final String RUN_ID_PATTERN = "^run_[A-Za-z0-9_]+$";

    private final AgentRunService agentRunService;
    private final BusinessDataService businessDataService;

    /**
     * Create a new AgentController with required service dependencies.
     *
     * @param agentRunService    service responsible for starting agent runs and polling run status
     * @param businessDataService service responsible for approving experiment plans and related business data operations
     */
    public AgentController(AgentRunService agentRunService, BusinessDataService businessDataService) {
        this.agentRunService = agentRunService;
        this.businessDataService = businessDataService;
    }

    /**
     * Starts an agent run using the provided request and returns an accepted run acknowledgement.
     *
     * @param request the payload describing the agent run configuration
     * @return a ResponseEntity whose body is an AgentRunAcceptedResponse containing the run identifier and initial metadata; the response uses HTTP 202 Accepted
     */
    @PostMapping("/run")
    public ResponseEntity<AgentRunAcceptedResponse> runAgent(
            @Valid @RequestBody AgentRunRequest request) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(agentRunService.runAgent(request));
    }

    /**
     * Retrieves the current status of the agent run identified by the provided ID.
     *
     * @param agentRunId the agent run identifier; must match the pattern "^run_[A-Za-z0-9_]+$"
     * @return the current AgentRunStatusResponse for the specified run
     */
    @GetMapping("/runs/{agentRunId}")
    public AgentRunStatusResponse getAgentRun(@PathVariable String agentRunId) {
        requireRunId(agentRunId);
        return agentRunService.poll(agentRunId);
    }

    /**
     * Approves the experiment plan associated with the given agent run.
     *
     * @param agentRunId the agent run identifier; must match the pattern "^run_[A-Za-z0-9_]+$"
     * @param request    the approval request containing approval decision and related metadata
     * @return           the approval response containing the approved experiment plan details and status
     */
    @PostMapping("/actions/{agentRunId}/approve")
    public ApproveExperimentPlanResponse approve(
            @PathVariable String agentRunId,
            @Valid @RequestBody ApproveExperimentPlanRequest request) {
        requireRunId(agentRunId);
        return businessDataService.approve(agentRunId, request);
    }

    /**
     * Ensures the provided agentRunId is not null and conforms to the expected run identifier format.
     *
     * @param agentRunId the agent run identifier to validate; expected to start with "run_" followed by letters, digits, or underscores
     * @throws ApiException if agentRunId is null or does not match the required pattern
     */
    private void requireRunId(String agentRunId) {
        if (agentRunId == null || !agentRunId.matches(RUN_ID_PATTERN)) {
            throw ApiException.badRequest("invalid agent_run_id: " + agentRunId);
        }
    }
}
