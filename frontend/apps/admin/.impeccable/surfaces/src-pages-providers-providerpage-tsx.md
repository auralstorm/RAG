---
version: 1
slug: 'src-pages-providers-providerpage-tsx'
primary_target: 'src/pages/providers/ProviderPage.tsx'
related_targets:
  [
    'src/modules/modelGateway/ProviderManagement.tsx',
    'src/modules/modelGateway/ProviderEditor.tsx',
  ]
---

# Provider 管理

Mode: Operate。面向超级管理员维护供应商连接设置，审计员只读。沿用现有 Admin 视觉系统及用户指定的 Ant Design Pro table-list；真实调用、模型子表由 P2-02/P2-07 接续。

## Direction contract

THESIS: 快速查找、维护和停用供应商，凭据始终只显示配置状态，不添加虚构统计。

OWN-WORLD: 继承现有浅色 Admin、系统字体、蓝色主操作和 ProLayout，使用 ProTable 搜索区、工具栏、状态与分页。

STORY: 查看列表与筛选；按权限新建或编辑；明确确认配置、启停和删除；失败回查，撤权后隐藏数据。

FIRST VIEWPORT: 顶部标题和说明，随后名称/类型/状态查询区；供应商列表工具栏右侧为新建按钮，表格横向滚动保留列宽。320/390/768/1440px 无页面横向溢出。

FORM: seed: none (pinned)。用户指定“前端页面参考” https://github.com/ant-design/ant-design-pro/blob/master/src/pages/table-list/index.tsx ，使用 antd 与 ProComponents，保持 Vite、不引入 Umi。表单使用聚焦弹窗，提交中阻止重复操作，失败清空凭据。

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

无新增栅格图片。当前实现不承诺已通过供应商真实调用或模型联动验收。
