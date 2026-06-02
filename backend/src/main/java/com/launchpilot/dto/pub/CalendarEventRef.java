package com.launchpilot.dto.pub;

public record CalendarEventRef(
        String eventId,
        String title,
        String scheduledAt) {}
