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

    /**
     * Create a compact UTC timestamp with a four-digit sequence component.
     *
     * The value combines the current UTC date/time formatted as `yyyyMMdd_HHmmss`,
     * an underscore, and a zero-padded 4-digit counter that cycles through 0000–9999.
     *
     * @return a string in the form yyyyMMdd_HHmmss_0000–9999 representing UTC time and a four-digit sequence number
     */
    private String stamp() {
        return OffsetDateTime.now(ZoneOffset.UTC).format(TS)
                + "_" + String.format("%04d", counter.incrementAndGet() % 10000);
    }

    /**
     * Generate a new run identifier prefixed with "run_".
     *
     * @return a string of the form `run_yyyyMMdd_HHmmss_NNNN` where the timestamp is UTC formatted as `yyyyMMdd_HHmmss`
     *         and `NNNN` is a zero-padded 4-digit sequence value (00-9999)
     */
    public String newRunId() {
        return "run_" + stamp();
    }

    /**
     * Generate an import identifier prefixed with "imp_" using the current UTC timestamp and a four-digit counter.
     *
     * @return the import id formatted as "imp_yyyyMMdd_HHmmss_NNNN"
     */
    public String newImportId() {
        return "imp_" + stamp();
    }

    /**
     * Create a new request identifier prefixed with `req_`.
     *
     * @return the identifier in the form req_yyyyMMdd_HHmmss_XXXX where `yyyyMMdd_HHmmss` is the UTC timestamp and `XXXX` is a zero-padded 4-digit counter (0000–9999)
     */
    public String newRequestId() {
        return "req_" + stamp();
    }

    /**
     * Create a deterministic brief identifier derived from an agent run identifier.
     *
     * @param agentRunId an agent run identifier; may include the leading "run_" prefix
     * @return `brief_<stamp>` where `<stamp>` is the agent run id with a leading "run_" removed if present (for example, `brief_20260601_001`)
     */
    public String briefIdFor(String agentRunId) {
        return "brief_" + stripRunPrefix(agentRunId);
    }

    /**
     * Create a deterministic calendar event identifier for a specific experiment row.
     *
     * The returned identifier is formed by removing a leading "run_" prefix from the provided
     * agentRunId (if present), prefixing the remainder with "cal_", and appending "_" followed by
     * the supplied index.
     *
     * @param agentRunId the agent run identifier that may start with "run_"
     * @param index the zero-based (or contextual) row/index value to append to the id
     * @return the calendar event id in the form `cal_<agentRunIdWithoutRunPrefix>_<index>`
     */
    public String calendarEventId(String agentRunId, int index) {
        return "cal_" + stripRunPrefix(agentRunId) + "_" + index;
    }

    /**
     * Generate a deterministic post identifier from an import id and CSV row number.
     *
     * @param importId the import identifier expected to begin with "imp_"; the suffix after that prefix is used in the generated id
     * @param rowNumber the CSV row number to include in the generated id
     * @return the post id in the form post_<importSuffix>_<rowNumber>, where <importSuffix> is the part of importId after the "imp_" prefix
     */
    public String postId(String importId, int rowNumber) {
        return "post_" + importId.substring("imp_".length()) + "_" + rowNumber;
    }

    /**
     * Remove a leading "run_" prefix from an agent run identifier, if present.
     *
     * @param agentRunId the agent run identifier which may start with "run_"
     * @return the identifier without the leading "run_" if present, otherwise the original identifier
     */
    private String stripRunPrefix(String agentRunId) {
        return agentRunId.startsWith("run_") ? agentRunId.substring("run_".length()) : agentRunId;
    }
}
