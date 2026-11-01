export type Expense = {
  id: string
  category: string
  estimated_cost: number
  actual_cost: number
  payment_status: string
  notes: string
}

export type Task = {
  id: string
  title: string
  description: string
  deadline: string | null
  priority: string
  status: string
  dependencies: string[]
}

export type Guest = {
  id: string
  name: string
  contact: string
  group_category: string
  rsvp_status: string
  meal_preference: string
  dietary_restrictions: string
  accommodation_required: boolean
  table_name: string
}

export type Vendor = {
  id: string
  name: string
  category: string
  location: string
  contact: string
  price_min: number
  price_max: number
  rating: number | null
  source: string
  verification_status: string
  services: string
  notes: string
  booking_status: string
  agreed_price: number
}

export type Idea = {
  id: string
  title: string
  summary: string
  estimated_cost: number
  budget_fit: string
  palette: string[]
  decoration: string[]
  food: string
  experience: string[]
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  tool_data?: Record<string, unknown>
}

export type ScheduleItem = {
  time: string
  activity: string
  owner: string
  status: string
}

export type ScheduleDay = {
  day: number
  label: string
  items: ScheduleItem[]
}

export type EventRecord = {
  id: string
  title: string
  event_type: string
  location: string
  event_date: string | null
  duration_days: number
  guest_count: number
  total_budget: number
  theme: string
  food_preferences: string
  accommodation_required: boolean
  accommodation_count: number
  decoration_preferences: string
  entertainment_requirements: string
  special_instructions: string
  status: string
  ideas: Idea[]
  is_demo: boolean
  progress_pct?: number
  expenses: Expense[]
  tasks: Task[]
  guests: Guest[]
  vendors: Vendor[]
  schedule: ScheduleDay[]
  messages: ChatMessage[]
}

export type DashboardMetrics = {
  event_count: number
  planned_budget: number
  allocated: number
  actual_spend: number
  remaining_budget: number
  pending_tasks: number
  overdue_tasks: number
  guest_count: number
  progress_pct: number
}

export type DashboardResponse = {
  events: Array<Partial<EventRecord> & { id: string; title: string; event_type: string; is_demo: boolean }>
  event: EventRecord | null
  metrics: DashboardMetrics
}
