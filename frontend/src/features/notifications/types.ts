export type NotificationRelatedEntity = {
  type: string;
  id: string;
};

export type WorkflowNotification = {
  id: string;
  type: string;
  title: string;
  body: string | null;
  is_read: boolean;
  related_entity: NotificationRelatedEntity | null;
  created_at: string;
  read_at: string | null;
};

export type NotificationList = {
  items: WorkflowNotification[];
  pagination: {
    limit: number;
    offset: number;
    returned: number;
    total: number;
  };
  unread_count: number;
};
