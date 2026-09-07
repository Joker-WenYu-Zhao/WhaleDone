import React from 'react';
import { Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom';
import IntersectObserver from '@/components/common/IntersectObserver';
import { Toaster } from '@/components/ui/sonner';

import { routes } from './routes';

// import { AuthProvider } from '@/contexts/AuthContext';
// import { RouteGuard } from '@/components/common/RouteGuard';

const App: React.FC = () => {
  return (
    // basename 取自 vite base（构建时为 /WhaleDone/）：
    // 否则 GitHub Pages 子路径访问时 /WhaleDone/ 匹配不上路由，被下方 * 兜底重定向到根域名
    <Router basename={import.meta.env.BASE_URL}>
      {/*<AuthProvider>*/}
      {/*<RouteGuard>*/}
      <IntersectObserver />
      <div className="flex flex-col min-h-screen">
        {/*<Header />*/}
        <main className="flex-grow">
          <Routes>
          {routes.map((route, index) => (
            <Route
              key={index}
              path={route.path}
              element={route.element}
            />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      {/* 提示浮层统一顶部居中（批量迁移等操作反馈在视线上方，不易遗漏） */}
      <Toaster position="top-center" />
      {/*</RouteGuard>*/}
      {/*</AuthProvider>*/}
    </Router>
  );
};

export default App;
