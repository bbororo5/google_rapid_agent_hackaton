package com.launchpilot.persistence.elastic;

import com.launchpilot.contracts.elastic.ContentPostDoc;
import java.util.List;

/** Persistence port for imported content evidence rows. */
public interface ContentPostRepository {
    IndexResult bulkIndex(List<ContentPostDoc> posts);
}
