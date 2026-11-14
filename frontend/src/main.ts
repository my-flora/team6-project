/**
 * 前端应用入口 —— 总装层（挂路由 / 挂组件）。
 *
 * 说明：
 * - 路由表占位已按六人分工的 view 目录预注册；
 * - 徐欣雨（展示侧）在 src/views/{dashboard,blackboard,...} 里实现 render 函数后，把 import 换成真实视图即可；
 * - 江艳菲（交互侧）的页面（gate / s1-input / s4-review / s6-signoff）同理；
 * - 所有数据请求一律走 @/api 的 apiClient，不得自行 fetch。
 */
import { apiClient } from "@/api";
import "./style.css";

type ViewRenderer = (root: HTMLElement) => void;

/** 路由表：hash → 视图渲染函数（当前为占位，待各 Owner 替换） */
const routes: Record<string, { title: string; owner: string; render?: ViewRenderer }> = {
  "/dashboard":     { title: "主页 · 阶段进度条",       owner: "徐欣雨⑤" },
  "/blackboard":    { title: "共享黑板 · 四色状态",     owner: "徐欣雨⑤" },
  "/s2-discussion": { title: "讨论区 · 议题与轮次",     owner: "徐欣雨⑤" },
  "/s3-proposal":   { title: "方案页 · 结构化裁剪",     owner: "徐欣雨⑤" },
  "/s5-prd":        { title: "PRD 阅读页",             owner: "徐欣雨⑤" },
  "/s1-input":      { title: "阶段1 · 结构化输入表单",  owner: "江艳菲⑥" },
  "/s4-review":     { title: "阶段4 · 红蓝对抗评审页",  owner: "江艳菲⑥" },
  "/s6-signoff":    { title: "阶段6 · 三方会签页",      owner: "江艳菲⑥" },
  "/gate":          { title: "门禁面板 · 红点与驳回",   owner: "江艳菲⑥" },
};

function renderRoute(): void {
  const app = document.querySelector<HTMLElement>("#app");
  if (!app) return;

  const path = location.hash.replace(/^#/, "") || "/dashboard";
  const route = routes[path];

  const nav = Object.entries(routes)
    .map(([p, r]) => `<a href="#${p}" class="${p === path ? "active" : ""}">${r.title}</a>`)
    .join("");

  app.innerHTML = `
    <header>
      <h1>虚拟项目室</h1>
      <div id="health" class="health">后端连接检测中…</div>
    </header>
    <nav>${nav}</nav>
    <main>
      ${
        route
          ? `<h2>${route.title}</h2><p class="placeholder">页面占位中 —— Owner：${route.owner}（在 src/views/ 下实现后替换 main.ts 中的路由注册）</p>`
          : `<h2>404</h2><p>未知路径 ${path}</p>`
      }
    </main>
  `;

  apiClient
    .health()
    .then((h) => {
      const el = document.querySelector<HTMLElement>("#health");
      if (el) el.textContent = `后端 OK · 契约版本 ${h.contracts_version}`;
    })
    .catch(() => {
      const el = document.querySelector<HTMLElement>("#health");
      if (el) el.textContent = "后端未启动（请运行 uvicorn backend.app:app --port 8000）";
    });
}

window.addEventListener("hashchange", renderRoute);
renderRoute();
