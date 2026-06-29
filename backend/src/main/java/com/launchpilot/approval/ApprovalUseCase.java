package com.launchpilot.approval;

import com.launchpilot.dto.common.ApprovalCommitResult;

/** Handles deterministic human approval actions. */
public interface ApprovalUseCase {
    ApprovalCommitResult approve(ApproveCommand command);
}
