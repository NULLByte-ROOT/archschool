import BellSchedulePanel from "../components/BellSchedulePanel";
import PageHeader from "../components/PageHeader";

export default function BellSchedulePage() {
  return (
    <div>
      <PageHeader
        kicker="admin"
        title="زنگ‌های مدرسه"
        subtitle="زمان‌بندی زنگ‌ها؛ ساعت شروع هر زنگ مبنای شمارش معکوس تکالیف است"
      />
      <BellSchedulePanel />
    </div>
  );
}
