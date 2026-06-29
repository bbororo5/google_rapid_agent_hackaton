package com.launchpilot.importing;

import com.launchpilot.contracts.elastic.ContentPostDoc;
import java.util.List;

/** Persistence port for imported content evidence rows. */
public interface ContentPostRepository {
    IndexResult bulkIndex(List<ContentPostDoc> posts);
}
