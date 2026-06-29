package com.launchpilot.dto.common;

import com.launchpilot.contracts.frontend.CalendarEventRef;
import java.util.List;

/** 계약 01 asyncapi: 승인 적재 결과 (approval.committed 이벤트 페이로드). P4 해결. */
public record ApprovalCommitResult(
        String approvalId,
        String growthBriefId,
        List<CalendarEventRef> createdCalendarEvents,
        String persistedAt) {}
