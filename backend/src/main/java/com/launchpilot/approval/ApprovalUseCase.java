package com.launchpilot.approval;

import com.launchpilot.contracts.shared.ApprovalCommitResult;

/** Handles deterministic human approval actions. */
public interface ApprovalUseCase {
    ApprovalCommitResult approve(ApproveCommand command);
}
