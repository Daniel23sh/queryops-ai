import type { QueryTemplate, QueryTemplateCategory } from "../types";

export function groupTemplatesByCategory(
  templates: QueryTemplate[]
): QueryTemplateCategory[] {
  const categoryMap = new Map<string, QueryTemplate[]>();

  for (const template of templates) {
    const category = template.category || "Uncategorized";
    const categoryTemplates = categoryMap.get(category) ?? [];
    categoryTemplates.push(template);
    categoryMap.set(category, categoryTemplates);
  }

  return Array.from(categoryMap, ([category, categoryTemplates]) => ({
    category,
    templates: categoryTemplates
  }));
}
