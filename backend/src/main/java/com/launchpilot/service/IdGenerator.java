package com.launchpilot.service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/**
 * 계약 03 ID 규칙. 같은 논리 연산의 재시도는 결정적 ID를 보장해야 한다.
 * - run/imp/req: 시간 + 카운터 (신규 생성).
 * - brief/cal: agent_run_id 파생 (결정적, 멱등).
 */
@Component
public class IdGenerator {

    private static final DateTimeFormatter TS =
            DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss");
    private final AtomicLong counter = new AtomicLong();

    private String stamp() {
        return OffsetDateTime.now(ZoneOffset.UTC).format(TS)
                + "_" + String.format("%04d", counter.incrementAndGet() % 10000);
    }

    public String newRunId() {
        return "run_" + stamp();
    }

    public String newImportId() {
        return "imp_" + stamp();
    }

    public String newRequestId() {
        return "req_" + stamp();
    }

    /** run_20260601_001 -> brief_20260601_001 (결정적). */
    public String briefIdFor(String agentRunId) {
        return "brief_" + stripRunPrefix(agentRunId);
    }

    /** 실험 1건당 결정적 캘린더 이벤트 ID. */
    public String calendarEventId(String agentRunId, int index) {
        return "cal_" + stripRunPrefix(agentRunId) + "_" + index;
    }

    /** CSV 행 post_id 부재 시 결정적 생성. */
    public String postId(String importId, int rowNumber) {
        return "post_" + importId.substring("imp_".length()) + "_" + rowNumber;
    }

    private String stripRunPrefix(String agentRunId) {
        return agentRunId.startsWith("run_") ? agentRunId.substring("run_".length()) : agentRunId;
    }
}
