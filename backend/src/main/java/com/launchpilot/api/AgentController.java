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

    public AgentController(AgentRunService agentRunService, BusinessDataService businessDataService) {
        this.agentRunService = agentRunService;
        this.businessDataService = businessDataService;
    }

    @PostMapping("/run")
    public ResponseEntity<AgentRunAcceptedResponse> runAgent(
            @Valid @RequestBody AgentRunRequest request) {
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(agentRunService.runAgent(request));
    }

    @GetMapping("/runs/{agentRunId}")
    public AgentRunStatusResponse getAgentRun(@PathVariable String agentRunId) {
        requireRunId(agentRunId);
        return agentRunService.poll(agentRunId);
    }

    @PostMapping("/actions/{agentRunId}/approve")
    public ApproveExperimentPlanResponse approve(
            @PathVariable String agentRunId,
            @Valid @RequestBody ApproveExperimentPlanRequest request) {
        requireRunId(agentRunId);
        return businessDataService.approve(agentRunId, request);
    }

    private void requireRunId(String agentRunId) {
        if (agentRunId == null || !agentRunId.matches(RUN_ID_PATTERN)) {
            throw ApiException.badRequest("invalid agent_run_id: " + agentRunId);
        }
    }
}
