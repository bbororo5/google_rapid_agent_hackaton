package com.launchpilot.persistence.elastic;

import com.launchpilot.contracts.elastic.CalendarEventDoc;
import com.launchpilot.contracts.elastic.GrowthBriefDoc;
import java.util.List;

/** Persistence port for approved immutable business documents. */
public interface ApprovalDocumentRepository {
    boolean growthBriefExistsForThread(String threadId);

    void persistApproval(GrowthBriefDoc brief, List<CalendarEventDoc> events);
}
