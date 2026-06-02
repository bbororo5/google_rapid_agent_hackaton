package com.launchpilot.dto.pub;

import com.launchpilot.dto.common.DateRange;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record AgentRunRequest(
        @NotBlank String workspaceId,
        @NotBlank String campaignId,
        @NotBlank @Size(max = 2000) String question,
        @NotNull DateRange dateRange,
        @Pattern(regexp = "^brief_[A-Za-z0-9_]+$") String parentBriefId) {}
