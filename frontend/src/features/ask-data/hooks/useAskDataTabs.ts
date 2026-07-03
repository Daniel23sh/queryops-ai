import { useEffect, useState } from "react";

import type { AskDataResultTab } from "../types";

export function useAskDataTabs(canViewTechnicalDetails: boolean) {
  const [activeTab, setActiveTab] = useState<AskDataResultTab>("results");
  const activeVisibleTab =
    !canViewTechnicalDetails && (activeTab === "sql" || activeTab === "diagnostics")
      ? "results"
      : activeTab;

  useEffect(() => {
    if (activeVisibleTab !== activeTab) {
      setActiveTab(activeVisibleTab);
    }
  }, [activeTab, activeVisibleTab]);

  return {
    activeTab: activeVisibleTab,
    setActiveTab
  };
}
