package com.launchpilot.persistence.elastic;

import com.launchpilot.dto.elastic.CalendarEventDoc;
import com.launchpilot.dto.elastic.GrowthBriefDoc;
import java.util.List;

/** Persistence port for approved immutable business documents. */
public interface ApprovalDocumentRepository {
    boolean growthBriefExistsForThread(String threadId);

    void persistApproval(GrowthBriefDoc brief, List<CalendarEventDoc> events);
}
