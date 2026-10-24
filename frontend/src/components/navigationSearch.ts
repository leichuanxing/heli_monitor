export interface NavigationItem { path: string; title: string; group: string }
export function searchNavigation(items: NavigationItem[], query: string): NavigationItem[] {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return items.filter(item => terms.every(term => `${item.title} ${item.group} ${item.path}`.toLocaleLowerCase().includes(term)))
}
