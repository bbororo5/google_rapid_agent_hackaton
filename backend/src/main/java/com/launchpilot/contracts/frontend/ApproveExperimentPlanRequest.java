package com.launchpilot.contracts.frontend;

import com.launchpilot.dto.common.ExperimentItem;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import java.util.List;

public record ApproveExperimentPlanRequest(
        @NotBlank @Pattern(regexp = "^plan_[A-Za-z0-9_]+$") String experimentPlanId,
        @NotBlank String approvedBy,
        @NotEmpty List<ExperimentItem> finalExperiments) {}
