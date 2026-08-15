/**
 * Seeded admin console data.
 *
 * Everything here is platform-level aggregate reporting that has no equivalent
 * in the job listings themselves. It is replaced by the analytics and reports
 * endpoints in Phase 8; the component shapes do not change.
 */

import type {
  ActivityItem,
  AdminNavItem,
  CategoryStat,
  ConversionStat,
  JobReport,
  LocationShare,
  LocationStat,
  MetricCard,
  SearchKeyword,
  SourceStat,
  TopJobRow,
} from '@/types/admin'

export const NAV_ITEMS: AdminNavItem[] = [
  { key: 'dashboard', label: 'Dashboard', icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' },
  { key: 'jobs', label: 'Jobs', icon: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2' },
  { key: 'add-job', label: 'Add Job', icon: 'M12 5v14M5 12h14' },
  { key: 'reports', label: 'Reports', icon: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z' },
  { key: 'analytics', label: 'Analytics', icon: 'M18 20V10M12 20V4M6 20v-6' },
  { key: 'categories', label: 'Categories', icon: 'M4 6h16M4 12h16M4 18h7' },
  { key: 'locations', label: 'Locations', icon: 'M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z' },
  { key: 'sources', label: 'Sources', icon: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71' },
  { key: 'settings', label: 'Settings', icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z' },
]

export const METRIC_CARDS: MetricCard[] = [
  { label: 'Total Jobs', value: '14,280', change: '+1,240 this month', trend: 'up', icon: '📋' },
  { label: 'Active Jobs', value: '12,948', change: '91% of total', trend: 'up', icon: '✅' },
  { label: 'Added Today', value: '48', change: '+12 vs yesterday', trend: 'up', icon: '⚡' },
  { label: 'Apply Clicks', value: '8,920', change: '+6.2% this week', trend: 'up', icon: '👆' },
  { label: 'Visitors Today', value: '6,240', change: 'Peak: 11am–1pm', trend: 'up', icon: '👀' },
  { label: 'Reported Jobs', value: '12', change: '3 need review', trend: 'warn', icon: '🚩' },
]

export const TOP_JOBS_TABLE: TopJobRow[] = [
  { title: 'Senior Frontend Engineer', company: 'Systems Limited', clicks: 312, views: 1840, saved: 94, status: 'featured' },
  { title: 'Product Designer (UX/UI)', company: 'Careem', clicks: 248, views: 1420, saved: 81, status: 'featured' },
  { title: 'DevOps Engineer', company: 'TechNation', clicks: 189, views: 986, saved: 52, status: 'published' },
  { title: 'Data Analyst', company: 'Daraz', clicks: 156, views: 874, saved: 44, status: 'verified' },
  { title: 'Software Engineer – Backend', company: 'Netsol', clicks: 142, views: 762, saved: 38, status: 'published' },
]

export const ACTIVITY_FEED: ActivityItem[] = [
  { type: 'add', msg: '12 new jobs added from Naukri.pk scraper', time: '2 min ago', tone: 'success' },
  { type: 'click', msg: 'Systems Limited – Frontend: 48 apply clicks today', time: '18 min ago', tone: 'brand' },
  { type: 'warn', msg: 'Ignite Internship listing expires in 2 days', time: '1 hr ago', tone: 'warning' },
  { type: 'add', msg: '5 government jobs added from FPSC', time: '3 hrs ago', tone: 'success' },
  { type: 'report', msg: 'Job reported: "Broken application link" – Arpatech', time: '4 hrs ago', tone: 'danger' },
  { type: 'click', msg: 'Careem Product Designer: 92 apply clicks today', time: '5 hrs ago', tone: 'brand' },
  { type: 'add', msg: 'Weekly auto-report generated – 62k sessions', time: '8 hrs ago', tone: 'accent' },
]

export const SEARCH_KEYWORDS: SearchKeyword[] = [
  { kw: 'Software Engineer', count: 3820 },
  { kw: 'Data Analyst', count: 2140 },
  { kw: 'Remote Jobs', count: 1980 },
  { kw: 'Marketing Manager', count: 1540 },
  { kw: 'Fresh Graduate', count: 1320 },
  { kw: 'Government Jobs', count: 1280 },
]

export const REPORTS_DATA: JobReport[] = [
  { id: 1, job: 'Junior Software Developer', company: 'Arpatech', reason: 'Broken Link', comment: 'The apply button leads to a 404 page on the company site.', date: '13 Aug 2026', category: 'Broken Link' },
  { id: 2, job: 'Marketing Assistant', company: 'Unknown', reason: 'Spam', comment: 'This looks like a fake job posting, no company info found.', date: '12 Aug 2026', category: 'Spam' },
  { id: 3, job: 'Senior Accountant', company: 'PwC Pakistan', reason: 'Expired', comment: 'I applied and got told the position was filled weeks ago.', date: '11 Aug 2026', category: 'Expired' },
  { id: 4, job: 'Data Entry Operator', company: 'ABC Corp', reason: 'Wrong Information', comment: 'Salary shown is PKR 80k but the actual offer was PKR 40k.', date: '10 Aug 2026', category: 'Wrong Information' },
]

export const CATEGORIES_DATA: CategoryStat[] = [
  { name: 'IT & Technology', count: 2840, status: 'Active', popularity: 92 },
  { name: 'Design', count: 634, status: 'Active', popularity: 64 },
  { name: 'Finance & Accounting', count: 890, status: 'Active', popularity: 71 },
  { name: 'Marketing', count: 712, status: 'Active', popularity: 68 },
  { name: 'Human Resources', count: 456, status: 'Active', popularity: 52 },
  { name: 'Government', count: 1200, status: 'Active', popularity: 84 },
  { name: 'Data & Analytics', count: 398, status: 'Active', popularity: 55 },
  { name: 'Content & Writing', count: 284, status: 'Archived', popularity: 38 },
]

export const LOCATIONS_DATA: LocationStat[] = [
  { name: 'Lahore', region: 'Punjab', type: 'City', jobs: 4820 },
  { name: 'Karachi', region: 'Sindh', type: 'City', jobs: 3940 },
  { name: 'Islamabad', region: 'Federal', type: 'City', jobs: 2310 },
  { name: 'Remote – Pakistan', region: 'Nationwide', type: 'Remote', jobs: 2840 },
  { name: 'Remote – Worldwide', region: 'International', type: 'Remote', jobs: 640 },
  { name: 'Rawalpindi', region: 'Punjab', type: 'City', jobs: 820 },
  { name: 'Peshawar', region: 'KPK', type: 'City', jobs: 420 },
  { name: 'Multan', region: 'Punjab', type: 'City', jobs: 310 },
]

export const SOURCES_DATA: SourceStat[] = [
  { name: 'Company Website', jobs: 6420, clicks: 48200, ctr: '7.5%', status: 'Active' },
  { name: 'LinkedIn', jobs: 3840, clicks: 32100, ctr: '8.4%', status: 'Active' },
  { name: 'Rozee.pk', jobs: 2100, clicks: 14800, ctr: '7.0%', status: 'Active' },
  { name: 'Mustakbil', jobs: 980, clicks: 5400, ctr: '5.5%', status: 'Active' },
  { name: 'WhatsApp Community', jobs: 420, clicks: 8200, ctr: '19.5%', status: 'Active' },
  { name: 'University Career Portal', jobs: 240, clicks: 2100, ctr: '8.8%', status: 'Active' },
]

export const CONVERSION_DATA: ConversionStat[] = [
  { label: 'Views → Apply Click', rate: '7.4%', count: '8,920 clicks', bar: 74 },
  { label: 'Apply Click Through Rate', rate: '18.2%', count: 'vs industry avg 12%', bar: 62 },
  { label: 'Save Rate', rate: '4.1%', count: '4,940 saves', bar: 41 },
  { label: 'Share Rate', rate: '1.8%', count: '2,160 shares', bar: 18 },
]

export const TOP_LOCATION_SHARE: LocationShare[] = [
  { loc: 'Lahore', pct: 38 },
  { loc: 'Karachi', pct: 29 },
  { loc: 'Remote', pct: 18 },
  { loc: 'Islamabad', pct: 10 },
  { loc: 'Other', pct: 5 },
]
