import { Link } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const Dashboard = () => {
  return (
    <div className="min-h-screen bg-background px-4 py-10">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Панель управления</h1>
          <p className="text-muted-foreground mt-2">
            Быстрый доступ к поиску компаний, справочникам и API.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Поиск компаний</CardTitle>
              <CardDescription>Найдите компанию по УНП или названию.</CardDescription>
            </CardHeader>
            <CardContent>
              <Link to="/company">
                <Button>Перейти к поиску</Button>
              </Link>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Справочники данных</CardTitle>
              <CardDescription>Просматривайте справочники и коды.</CardDescription>
            </CardHeader>
            <CardContent>
              <Link to="/references">
                <Button variant="outline">Открыть справочники</Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
