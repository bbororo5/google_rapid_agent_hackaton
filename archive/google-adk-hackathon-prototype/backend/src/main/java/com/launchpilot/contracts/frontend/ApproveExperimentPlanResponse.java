package com.launchpilot.contracts.frontend;

import java.util.List;

public record ApproveExperimentPlanResponse(
        boolean ok,
        String message,
        String growthBriefId,
        List<CalendarEventRef> createdCalendarEvents,
        String persistedAt) {}
