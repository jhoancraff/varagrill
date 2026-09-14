# Graph Report - varagrill  (2026-09-11)

## Corpus Check
- 130 files · ~357,045 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 3746 nodes · 6279 edges · 297 communities (129 shown, 76 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 181 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- New Order Page
- Jquery-3.7.1.Min
- Edit Order Page
- Api Views
- Facturacion Views
- Impresion Termica
- Restaurant
- Contabilidad
- Api Views
- Checkout Page
- Mesas Atendidas Page
- Xregexp
- Analyst Edit Product Page
- Analyst Edit Recipe Page
- Analyst New Recipe Page
- Jquery
- Restaurant
- Analyst New Product Page
- Analyst Preparations Page
- Reporte Cuadre Caja Rango Page
- Reportes
- Analyst Gastos Page
- Analyst Edit Ingredient Page
- Analyst Products Page
- Kitchen Orders Page
- Select2.Full
- Analyst Promotions Page
- Analyst Margen Ganancia Page
- Analyst Mesas Page
- Analyst Users Page
- Reporte Cuadre Caja Page
- Ingredientes Excel
- Estado Resultados Page
- Jquery.Min
- Admin Panel Page
- Analyst Ingredients Page
- Reporte Disponibilidad Cuentas Page
- Analys Printers Page
- Analyst Bulk Promotion Page
- Analyst Chef Recommendations Page
- Analyst Compras Borrador Page
- Analyst Ingredients Import Page
- Analyst New Mesa Page
- Contabilidad Panel Page
- Xregexp.Min
- Select2.Full
- Requirements.Txt
- Analyst Edit Preparation Page
- Analyst New Preparation Page
- Analyst Recipes Page
- Analyst Ingredients Bulk Create Page
- Analyst New Promotion Page
- Welcome Screen
- Select2.Full
- Select2.Full
- Analyst New Chef Recommendation Page
- Cuentas Por Cobrar Page
- Cuentas Por Pagar Page
- Select2.Full
- Package.Json
- Analyst New Ingredient Page
- Promotions Page
- Analyst Ingredients Report Page
- Analyst Preparations Report Page
- Historial Facturas Page
- New Order Page
- Kitchen Orders Page
- Compras Views
- Chef Recommendations Page
- Analyst Edit Mesa Page
- Analyst Edit User Page
- Analyst Ingredients Create Report Page
- Analyst New User Page
- Analyst Payment Methods Page
- Comprobante Pago Page
- Edit Order Page
- Select2.Full
- Select2.Full
- Select2.Full
- Jquery
- Select2.Full
- Select2.Full.Min
- Admin
- Auth Helpers
- Consumers
- Related Object Lookups
- Jquery
- Jquery.Min
- Analyst Compras Page
- Gastos Views
- Tests
- Analyst Inventory Hub Page
- Core
- Jquery
- Seed Tequenos La Vara
- Auth Form
- Actions
- Calendar
- Confirm Modal
- Tests
- Restaurant
- Analyst Edit Product Page
- Analyst New Product Page
- Unsaved Changes Modal
- Kitchen Ticket
- Settings
- 1785330845640.Jpg
- Currency
- Pagination
- Jquery
- Serializers
- Seed Beverages Data
- Seed Restaurant Data
- 0013 Metodos Pago Dinamicos Y Rol Cajera
- Unit Rescale
- Select2.Full
- Tests
- Ing
- Seed Carnes Pollos
- Tests
- Ajax-Form
- Unit Conversion
- Package.Json
- Core
- Jquery.Min
- Tests
- Kitchen Orders Page
- Theme
- Select2.Full
- Csrf
- Test Print
- 0002 Seed Roles
- 0014 Vgmetodopago Moneda
- 0023 Seed Categorias Gasto
- 0024 Seed Rol Contador
- Notifications
- Manage
- Cancel
- Nav Sidebar
- Urlify
- Wsgi
- Brand Header
- Edit Order Page
- New Order Page
- Select Box
- Jquery
- Jquery
- Bs
- Cs
- Hr
- Lt
- Lv
- Sr
- Sr- Cyrl
- Uk
- Select2.Full
- 0004 Vgpromocion Duracion Dias
- 0005 Alter Vgpromocion Fecha Fin
- 0018 Vgdetallepedido Costo Unitario Venta
- 0019 Vgdetallepedidoopcion Vggrupoopcionproducto And More
- 0020 Vgdetallepedidoopcion Producto And More
- 0021 Vgcompra Estado Pago Vgcompra Saldo Pendiente And More
- 0022 Vgcategoriagasto Vggasto Vgabonogasto
- 0026 Vgcategoriaproducto Arma Plato Automatico And More
- 0027 Vgcategoriaproducto Prioridad Comanda
- 0028 Vgingrediente Contenido Envase And More
- 0029 Vgcategoriaproducto No Requiere Cocina And More
- 0030 Vgingrediente Precio Compra
- Init
- Icon.Svg
- Vite.Config
- Date Time Shortcuts
- Autocomplete
- Change Form
- Core
- Filters
- Inlines
- Jquery.Init
- Popup Response
- Prepopulate
- Prepopulate Init
- Select Filter2
- Af
- Ar
- Az
- Bg
- Bn
- Ca
- Da
- De
- Dsb
- El
- En
- Es
- Et
- Eu
- Fa
- Fi
- Fr
- Gl
- He
- Hi
- Hsb
- Hu
- Id

## God Nodes (most connected - your core abstractions)
1. `_auth_response()` - 82 edges
2. `_is_admin_user()` - 67 edges
3. `useUnsavedChangesGuard()` - 48 edges
4. `useToast()` - 41 edges
5. `_is_cajera_user()` - 34 edges
6. `Meta` - 29 edges
7. `NewOrderPage()` - 24 edges
8. `useMobileBackHandler()` - 24 edges
9. `MesasAtendidasPage()` - 23 edges
10. `UnsavedChangesModal()` - 23 edges

## Surprising Connections (you probably didn't know these)
- `Django backend service (127.0.0.1:8000)` --conceptually_related_to--> `daphne 4.2.3`  [INFERRED]
  frontend/README.md → requirements.txt
- `Django backend service (127.0.0.1:8000)` --conceptually_related_to--> `Django 6.0.7`  [INFERRED]
  frontend/README.md → requirements.txt
- `Django backend service (127.0.0.1:8000)` --conceptually_related_to--> `gunicorn 26.0.0`  [INFERRED]
  frontend/README.md → requirements.txt
- `L()` --indirect_call--> `v()`  [INFERRED]
  staticfiles/admin/js/vendor/jquery/jquery.min.js → staticfiles/admin/js/vendor/select2/select2.full.min.js
- `ee()` --indirect_call--> `v()`  [INFERRED]
  staticfiles/rest_framework/js/jquery-3.7.1.min.js → staticfiles/admin/js/vendor/select2/select2.full.min.js

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **ASGI real-time stack: Django Channels over Daphne with Redis channel layer** — requirements_channels, requirements_channels_redis, requirements_daphne, requirements_redis [EXTRACTED 1.00]
- **Full-stack deployment: Nginx serves React dist and proxies API to Django** — frontend_readme, frontend_index, requirements_django [INFERRED 0.85]

## Communities (297 total, 76 thin omitted)

### Community 0 - "New Order Page"
Cohesion: 0.04
Nodes (85): _active_promotions_by_product(), _add_preparation_needs(), adicionales_disponibles_view(), admin_configuracion_costeo_view(), admin_products_view(), admin_recipes_view(), _aplicar_rendimiento_receta(), _avanzar_pedidos_en_preparacion_vencidos() (+77 more)

### Community 1 - "Jquery-3.7.1.Min"
Cohesion: 0.02
Nodes (85): addAddonButtonIconStyle, addIconStyle, addonChipStyle, addonPickerOptionPriceStyle, addonPickerOptionStyle, addonPickerPanelStyle, addonPriceStyle, addonSectionStyle (+77 more)

### Community 2 - "Edit Order Page"
Cohesion: 0.06
Nodes (61): e(), i(), l(), n(), r(), s(), u(), Ae() (+53 more)

### Community 3 - "Api Views"
Cohesion: 0.03
Nodes (70): addIconStyle, addonChipStyle, addonPriceStyle, addonSectionStyle, addonSelectStyle, armarPlatoBarStyle, armarPlatoButtonStyle, armarPlatoLabelStyle (+62 more)

### Community 4 - "Facturacion Views"
Cohesion: 0.03
Nodes (68): cancelOrderToggleStyle, checkoutButtonStyle, clienteFormStyle, clienteHintStyle, cobroPickerWrapStyle, cuentasPorCobrarWrapStyle, descuentoBlockStyle, descuentoCheckboxRowStyle (+60 more)

### Community 5 - "Impresion Termica"
Cohesion: 0.06
Nodes (61): _build_documento_venta_bytes(), _build_recibo_bytes(), enviar_trabajo_lpd(), _formatear_bs(), imprimir_factura_caja(), imprimir_nota_entrega_caja(), imprimir_prefactura_caja(), LpdError (+53 more)

### Community 6 - "Restaurant"
Cohesion: 0.06
Nodes (62): admin_metodos_pago_view(), ingresos_extra_view(), metodos_pago_activos_view(), _parse_fecha_reporte(), _parse_rango_o_fecha_reporte(), csrf_exempt, Vistas del modulo de Contabilidad: metodos de pago configurables y el cuadre de…, Conciliación bancaria por cuenta: compara, para cada banco real (ver… (+54 more)

### Community 7 - "Contabilidad"
Cohesion: 0.05
Nodes (53): URL configuration for config project. The `urlpatterns` list routes URLs to…, admin_categorias_view(), admin_chef_recommendations_view(), admin_impresora_caja_view(), admin_mesas_view(), admin_promotions_view(), admin_users_view(), compra_detail_view() (+45 more)

### Community 8 - "Api Views"
Cohesion: 0.10
Nodes (54): _is_admin_user(), _is_cajera_user(), clientes_buscar_view(), cuentas_por_cobrar_view(), datos_fiscales_view(), _emitir_factura(), factura_abono_view(), factura_anular_view() (+46 more)

### Community 9 - "Checkout Page"
Cohesion: 0.08
Nodes (21): AbstractUser, Sincroniza VGIngrediente con el conteo físico de…, Command, BaseCommand, Reemplaza a auth.User. Hereda username, first_name, last_name, email, password,…, Una elaboración intermedia (salsa, base, marinado, aderezo...) que no se vende…, Componentes de una VGPreparacion. Cada fila es un ingrediente crudo O otra…, Componentes de un VGProducto. Igual que en VGRecetaPreparacion: cada fila es un… (+13 more)

### Community 10 - "Mesas Atendidas Page"
Cohesion: 0.06
Nodes (45): addRoundButtonStyle(), backButtonStyle(), cancelMoveButtonStyle(), changeTableButtonStyle(), confirmMoveButtonStyle(), containerStyle(), editOrderButtonStyle(), emptyStateStyle (+37 more)

### Community 11 - "Xregexp"
Cohesion: 0.05
Nodes (44): backButtonStyle, cambiarCuentaButtonStyle, cancelarCambioButtonStyle, cellStyle, containerStyle(), dateInputStyle, dateLabelStyle, editInputStyle (+36 more)

### Community 12 - "Analyst Edit Product Page"
Cohesion: 0.06
Nodes (40): AnalystEditRecipePage(), backButtonStyle, badgeStyle, componentCardStyle, componentMetaStyle, componentsPanelStyle, componentTitleStyle, composerRowStyle() (+32 more)

### Community 13 - "Analyst Edit Recipe Page"
Cohesion: 0.05
Nodes (40): AnalystNewRecipePage(), backButtonStyle, badgeStyle, componentCardStyle, componentMetaStyle, componentsPanelStyle, componentTitleStyle, composerRowStyle() (+32 more)

### Community 14 - "Analyst New Recipe Page"
Cohesion: 0.08
Nodes (26): _arrayLikeToArray(), augment(), buildAstral(), cacheAstral(), cacheInvertedBmp(), charCode(), clipDuplicates(), copyRegex() (+18 more)

### Community 15 - "Jquery"
Cohesion: 0.05
Nodes (39): backButtonStyle, badgeStyle, componentCardStyle, componentMetaStyle, componentTitleStyle, confirmRemoveBoxStyle, confirmRemoveTextStyle, costReferenceBoxStyle (+31 more)

### Community 16 - "Restaurant"
Cohesion: 0.06
Nodes (39): backButtonStyle, badgeBase, bancoCardStyle(), bancoHeaderStyle, bancoNombreStyle, bancosGridStyle(), conciliadoBoxStyle, containerStyle() (+31 more)

### Community 17 - "Analyst New Product Page"
Cohesion: 0.06
Nodes (39): backButtonStyle, cellStyle, cobradasTableStyle, containerStyle(), dateInputStyle, dateLabelStyle, diferenciaStyle(), emptyStyle (+31 more)

### Community 18 - "Analyst Preparations Page"
Cohesion: 0.07
Nodes (38): backButtonStyle, cellStyle, containerStyle(), dateInputStyle, dateLabelStyle, desgloseGridStyle(), desgloseLabelStyle, desgloseSecondaryStyle (+30 more)

### Community 19 - "Reporte Cuadre Caja Rango Page"
Cohesion: 0.06
Nodes (38): backButtonStyle, cellStyle, containerStyle(), cxcTableStyle, dateInputStyle, dateLabelStyle, emptyStyle, ESTADO_LABEL (+30 more)

### Community 20 - "Reportes"
Cohesion: 0.08
Nodes (24): Meta, VGAuditoria, Meta, VGAuditoria, Auditoría de cada corrección de cuenta (metodo_pago) hecha desde el cuadre de…, Tipo de metodo de pago disponible al cobrar (Efectivo, Tarjeta, Binance, Zelle,…, Cierre único al final del día, lo hace la última persona del turno.…, Conciliación bancaria por cuenta/banco: compara lo que el sistema calcula que… (+16 more)

### Community 21 - "Analyst Gastos Page"
Cohesion: 0.08
Nodes (22): Modelos separados en dos archivos segun a que parte del negocio pertenecen: -…, Meta, VGAuditoria, Configuración de la impresora térmica de caja (recibo con detalle y montos que…, Configuración global de costeo de recetas: fila única (singleton, mismo…, Un grupo de opciones propio de un producto (ej: "Acompañante" en una sopa de…, Una opción concreta dentro de un VGGrupoOpcionProducto (ej: "Arepas" dentro del…, Factura de proveedor a medio armar: el analista va agregando ingredientes uno… (+14 more)

### Community 22 - "Analyst Edit Ingredient Page"
Cohesion: 0.07
Nodes (32): AjustePedidoModal(), errorStyle, fieldLabelStyle, infoNoteStyle, modalBackdropStyle, modalCardStyle, modalDescStyle, modalFooterStyle (+24 more)

### Community 23 - "Analyst Products Page"
Cohesion: 0.08
Nodes (36): abonoFormStyle(), AnalystGastosPage(), backButtonStyle, categoriaChipStyle(), categoriaTotalChipStyle, cellPrimaryStyle, cellStyle, collapseButtonStyle (+28 more)

### Community 24 - "Kitchen Orders Page"
Cohesion: 0.06
Nodes (13): computeStyleTests(), dataAttr(), finalPropName(), getData(), Identity(), leverageNative(), NOTE: This can be skipped if there are no unmatched elements (i.e.,…, TODO: Now that all calls to _data and _removeData have been replaced (+5 more)

### Community 25 - "Select2.Full"
Cohesion: 0.06
Nodes (35): backButtonStyle, badgeStyle, componentCardStyle, componentMetaStyle, componentTitleStyle, costReferenceBoxStyle, costReferenceHintStyle, costReferenceLabelStyle (+27 more)

### Community 26 - "Analyst Promotions Page"
Cohesion: 0.07
Nodes (35): AnalystProductsPage(), backButtonStyle, badgeStyle, containerStyle(), dangerButtonStyle, emptyStateStyle, filterSelectStyle, filtersRowStyle() (+27 more)

### Community 27 - "Analyst Margen Ganancia Page"
Cohesion: 0.08
Nodes (34): backButtonStyle, categoriaChipButtonStyle, categoriaChipStyle, containerStyle(), dateInputStyle, dateLabelStyle, emptyStyle, EstadoResultadosPage() (+26 more)

### Community 28 - "Analyst Mesas Page"
Cohesion: 0.09
Nodes (34): abonoFormStyle(), backButtonStyle(), compraCardStyle(), comprobanteLinkStyle, containerStyle(), CuentasPorPagarPage(), dateInputStyle, dateLabelStyle (+26 more)

### Community 29 - "Analyst Users Page"
Cohesion: 0.10
Nodes (20): Ae(), B(), Be(), $e(), F(), fe(), Ge(), ht() (+12 more)

### Community 30 - "Reporte Cuadre Caja Page"
Cohesion: 0.09
Nodes (32): abonoFormStyle(), backButtonStyle(), buscadorFormStyle(), containerStyle(), dateFieldStyle, dateLabelStyle, detailPanelStyle, detailTotalsStyle (+24 more)

### Community 31 - "Ingredientes Excel"
Cohesion: 0.08
Nodes (32): backButtonStyle, cellStyle, consignacionTableStyle, containerStyle(), dangerButtonStyle, dateInputStyle, dateLabelStyle, desgloseGridStyle() (+24 more)

### Community 32 - "Estado Resultados Page"
Cohesion: 0.12
Nodes (5): ArrayAdapter(), InputData(), SelectAdapter(), Tags(), Tokenizer()

### Community 33 - "Jquery.Min"
Cohesion: 0.06
Nodes (31): dependencies, react, react-dom, devDependencies, jsdom, serve, @testing-library/jest-dom, @testing-library/react (+23 more)

### Community 34 - "Admin Panel Page"
Cohesion: 0.09
Nodes (31): AnalystMovimientoProductosPage(), backButtonStyle, cellStyle, chipButtonStyle(), containerStyle(), dateInputStyle, dateLabelStyle, emptyStyle (+23 more)

### Community 35 - "Analyst Ingredients Page"
Cohesion: 0.08
Nodes (31): AnalystPromotionsPage(), backButtonStyle, badgeStyle, bulkBarStyle(), bulkTextStyle, containerStyle(), dangerButtonStyle, emptyStateStyle (+23 more)

### Community 36 - "Reporte Disponibilidad Cuentas Page"
Cohesion: 0.07
Nodes (31): backButtonStyle, cellStyle, containerStyle(), correccionNotaStyle, cuentaSelectStyle, dateInputStyle, dateLabelStyle, emptyStyle (+23 more)

### Community 37 - "Analys Printers Page"
Cohesion: 0.09
Nodes (30): AnalystMargenGananciaPage(), backButtonStyle, categoriaStyle, cellStyle, containerStyle(), dateInputStyle, dateLabelStyle, emptyStyle (+22 more)

### Community 38 - "Analyst Bulk Promotion Page"
Cohesion: 0.08
Nodes (30): AnalystMesasPage(), backButtonStyle, badgeStyle, containerStyle(), dangerButtonStyle, emptyStateStyle, estadoColors, estadoLabels (+22 more)

### Community 39 - "Analyst Chef Recommendations Page"
Cohesion: 0.08
Nodes (30): AnalystUsersPage(), backButtonStyle, badgeStyle, containerStyle(), dangerButtonStyle, emptyStateStyle, headerRowStyle(), noticeStyle (+22 more)

### Community 40 - "Analyst Compras Borrador Page"
Cohesion: 0.07
Nodes (18): backButtonStyle, cardBadgeStyle, cardButtonStyle, cardDescriptionStyle, cardHeaderStyle, cardIconWrapStyle, cardLinkStyle, cardTitleStyle (+10 more)

### Community 41 - "Analyst Ingredients Import Page"
Cohesion: 0.08
Nodes (30): backButtonStyle, cellStyle, containerStyle(), cuentaCardStyle(), cuentaDetalleStyle, cuentaHeaderStyle, cuentaNombreStyle, cuentaSaldoStyle() (+22 more)

### Community 42 - "Analyst New Mesa Page"
Cohesion: 0.07
Nodes (17): AdminPanelPage(), analystSections, backButtonStyle, cardButtonStyle, cardDescriptionStyle, cardHeaderStyle, cardIconWrapStyle, cardLinkStyle (+9 more)

### Community 43 - "Contabilidad Panel Page"
Cohesion: 0.08
Nodes (29): AnalystComprasBorradorPage(), backButtonStyle, cellPrimaryStyle, cellStyle, containerStyle(), dangerButtonStyle, emptyItemForm, emptyLote (+21 more)

### Community 44 - "Xregexp.Min"
Cohesion: 0.07
Nodes (29): backButtonStyle, badgeStyle, componentCardStyle, componentMetaStyle, componentsPanelStyle, componentTitleStyle, dangerButtonStyle, emptyDraft (+21 more)

### Community 45 - "Select2.Full"
Cohesion: 0.08
Nodes (28): AnalystIngredientsPage(), backButtonStyle, badgeStyle, containerStyle(), emptyForm, emptyStateStyle, fieldStyle, formGridStyle() (+20 more)

### Community 46 - "Requirements.Txt"
Cohesion: 0.09
Nodes (27): AnalystIngredientsReportPage(), backButtonStyle, cellActionsStyle, cellPrimaryStyle, cellStyle, containerStyle(), dangerButtonStyle, emptyStyle (+19 more)

### Community 47 - "Analyst Edit Preparation Page"
Cohesion: 0.08
Nodes (27): AnalysPrintersPage(), assignedPillStyle, autoPlatoCheckboxRowStyle, backButtonStyle, badgeStyle, cajaFieldStyle, cajaFormStyle(), cajaLabelStyle (+19 more)

### Community 48 - "Analyst New Preparation Page"
Cohesion: 0.08
Nodes (27): AnalystBulkPromotionPage(), backButtonStyle, badgeStyle, containerStyle(), emptyForm, emptyStateStyle, fieldStyle, formGridStyle() (+19 more)

### Community 49 - "Analyst Recipes Page"
Cohesion: 0.08
Nodes (27): AnalystChefRecommendationsPage(), backButtonStyle, badgeStyle, containerStyle(), dangerButtonStyle, emptyStateStyle, headerRowStyle(), noticeStyle (+19 more)

### Community 50 - "Analyst Ingredients Bulk Create Page"
Cohesion: 0.09
Nodes (27): AnalystEditPreparationPage(), componentRowStyle, composerStyle(), containerStyle(), costLabelStyle, costSummaryStyle, costValueStyle, dangerButtonStyle (+19 more)

### Community 51 - "Analyst New Promotion Page"
Cohesion: 0.09
Nodes (27): ACCION_LABELS, AnalystIngredientsImportPage(), backButtonStyle, cellPrimaryStyle, cellStyle, confirmRowStyle(), containerStyle(), countBadgeStyle() (+19 more)

### Community 52 - "Welcome Screen"
Cohesion: 0.10
Nodes (13): G(), _arrayLikeToArray(), augment(), cacheInvertedBmp(), charCode(), clipDuplicates(), copyRegex(), _createForOfIteratorHelper() (+5 more)

### Community 53 - "Select2.Full"
Cohesion: 0.09
Nodes (14): callDep(), ContainerCSS(), countResults(), DropdownCSS(), handler(), hasProp(), makeNormalize(), makeRelParts() (+6 more)

### Community 54 - "Select2.Full"
Cohesion: 0.13
Nodes (24): src/main.jsx entry script, manifest.webmanifest, #root mount div, varagrill-logo.jpg icon asset, Varagrill Frontend README, Django backend service (127.0.0.1:8000), Compiled frontend dist build (npm run build), Nginx reverse-proxy pattern for SPA + Django API (+16 more)

### Community 55 - "Analyst New Chef Recommendation Page"
Cohesion: 0.09
Nodes (26): AnalystNewPreparationPage(), componentRowStyle, composerStyle(), containerStyle(), costLabelStyle, costSummaryStyle, costValueStyle, dangerButtonStyle (+18 more)

### Community 56 - "Cuentas Por Cobrar Page"
Cohesion: 0.09
Nodes (26): AnalystRecipesPage(), backButtonStyle, badgeStyle, componentCountStyle, componentPreviewStyle, containerStyle(), dangerButtonStyle, emptyStateStyle (+18 more)

### Community 57 - "Cuentas Por Pagar Page"
Cohesion: 0.11
Nodes (26): abonoFormStyle(), backButtonStyle(), containerStyle(), CuentasPorCobrarPage(), dateFieldStyle, dateLabelStyle, detailPanelStyle, detailTotalsStyle (+18 more)

### Community 58 - "Select2.Full"
Cohesion: 0.16
Nodes (25): admin_catalog_view(), _costo_unitario_por_compra(), _finalizar_estado_pago_compra(), Precio de compra ÷ cantidad REALMENTE utilizable. Si el ingrediente tiene…, Deja lista la cuenta por pagar de una VGCompra recien creada: el saldo…, _serialize_abono_compra(), _serialize_compra(), admin_compra_borrador_agregar_view() (+17 more)

### Community 59 - "Package.Json"
Cohesion: 0.09
Nodes (25): ACCION_LABELS, AnalystIngredientsBulkCreatePage(), backButtonStyle, cellPrimaryStyle, cellStyle, confirmRowStyle(), containerStyle(), countBadgeStyle() (+17 more)

### Community 60 - "Analyst New Ingredient Page"
Cohesion: 0.09
Nodes (25): AnalystNewPromotionPage(), backButtonStyle, badgeStyle, containerStyle(), dangerButtonStyle, emptyForm, emptyStateStyle, fieldStyle (+17 more)

### Community 61 - "Promotions Page"
Cohesion: 0.10
Nodes (8): DecoratedClass(), Defaults(), Dropdown(), makeRequire(), oldMatcher(), wrappedMatcher(), Options(), Translation()

### Community 62 - "Analyst Ingredients Report Page"
Cohesion: 0.12
Nodes (4): AttachContainer(), InfiniteScroll(), MultipleSelection(), SingleSelection()

### Community 63 - "Analyst Preparations Report Page"
Cohesion: 0.09
Nodes (15): Command, BaseCommand, Entrega parcial de efectivo durante el turno (ej. cuando la caja acumula mucho…, Recibo de venta SIN efecto fiscal: lo que hoy se emite en el mostrador en vez…, Pago del restaurante hacia un gasto operativo (egreso). Modelo aparte de VGPago…, VGAbonoGasto, VGConsignacionCaja, VGNotaEntrega (+7 more)

### Community 64 - "Historial Facturas Page"
Cohesion: 0.10
Nodes (24): AnalystNewChefRecommendationPage(), backButtonStyle, badgeStyle, containerStyle(), emptyStateStyle, fieldStyle, formGridStyle(), headerRowStyle() (+16 more)

### Community 66 - "Kitchen Orders Page"
Cohesion: 0.10
Nodes (21): AnalystDatosFiscalesPage(), backButtonStyle, containerStyle(), emptyForm, emptyStyle, fieldStyle, formGridStyle(), inputStyle (+13 more)

### Community 67 - "Compras Views"
Cohesion: 0.11
Nodes (21): backButtonStyle, badgeStyle, cardBodyStyle, cardImagePlaceholderStyle, cardImageStyle, cardImageWrapStyle, cardStyle, categoryStyle (+13 more)

### Community 68 - "Chef Recommendations Page"
Cohesion: 0.10
Nodes (22): backButtonStyle, badgeStyle, cardBodyStyle, cardImagePlaceholderStyle, cardImageStyle, cardImageWrapStyle, cardStyle, categoryStyle (+14 more)

### Community 69 - "Analyst Edit Mesa Page"
Cohesion: 0.11
Nodes (21): addonBadgeStyle, AnalystPreparationsReportPage(), backButtonStyle, cellActionsStyle, cellPrimaryStyle, cellStyle, containerStyle(), dangerButtonStyle (+13 more)

### Community 70 - "Analyst Edit User Page"
Cohesion: 0.14
Nodes (21): backButtonStyle(), buscadorFormStyle(), containerStyle(), embeddedHeaderStyle, emptyStateStyle, errorStyle, estadoBadgeStyle(), estadoLabel() (+13 more)

### Community 71 - "Analyst Ingredients Create Report Page"
Cohesion: 0.12
Nodes (21): backButtonStyle(), cardHeaderButtonStyle, cardStyle, containerStyle(), detailNoteStyle, detailTotalsStyle, detailWrapStyle, emptyStateStyle (+13 more)

### Community 72 - "Analyst New User Page"
Cohesion: 0.10
Nodes (22): addAddonButtonStyle(), cartListStyle(), cartPanelStyle(), catalogTypeChipStyle(), computeItemTotal(), cryptoRandomId(), getCookie(), getQueuedOrders() (+14 more)

### Community 73 - "Analyst Payment Methods Page"
Cohesion: 0.11
Nodes (20): CAJERA_ALLOWED_VIEWS, featureCardButtonStyle, featureCardStyle, liveNoticeStyle, newOrderButtonStyle, notificationPromptAcceptStyle, notificationPromptBackdropStyle, notificationPromptCardStyle() (+12 more)

### Community 74 - "Comprobante Pago Page"
Cohesion: 0.11
Nodes (20): AnalystNewIngredientPage(), containerStyle(), duplicateLinkStyle, duplicateWarningStyle, emptyForm, fieldStyle, gridStyle(), helpTextStyle (+12 more)

### Community 75 - "Edit Order Page"
Cohesion: 0.11
Nodes (20): AnalystPaymentMethodsPage(), backButtonStyle, bancoButtonStyle, cellActionsStyle, cellStyle, containerStyle(), dangerButtonStyle, emptyStyle (+12 more)

### Community 76 - "Select2.Full"
Cohesion: 0.14
Nodes (12): admin_ingredientes_import_view(), _costo_unitario_desde_precio(), _importar_ingredientes(), _parse_trio_envase_peso_precio(), _preview_ingrediente_row(), precio_compra ÷ peso_real: caso particular de _costo_unitario_por_compra cuando…, Valida el trío contenido_envase/peso_real/precio_compra ya parseado a Decimal…, Parsea las 3 columnas opcionales del Excel "peso neto"/"peso real"/"precio de… (+4 more)

### Community 77 - "Select2.Full"
Cohesion: 0.15
Nodes (19): _cell_value(), _col_letters_to_index(), _first_sheet_path(), InvalidExcelError, _load_shared_strings(), _normalize_text(), normalize_unidad(), parse_cantidad() (+11 more)

### Community 78 - "Select2.Full"
Cohesion: 0.11
Nodes (11): Command, BaseCommand, Contador atómico por serie (ej: "FACTURA", "CONTROL", "PREFACTURA").…, Estructura común de una línea de venta (qué se vendió, a qué precio y cómo se…, precio_unitario ya es el precio final de venta (el mismo que se cobra en la…, Documento de venta con numeración fiscal. No depende de VGPedido: puede nacer…, VGCorrelativoFiscal, VGFactura (+3 more)

### Community 79 - "Jquery"
Cohesion: 0.13
Nodes (18): AnalystEditMesaPage(), backButtonStyle, badgeStyle, containerStyle(), emptyForm, emptyStateStyle, estadoOptions, fieldStyle (+10 more)

### Community 80 - "Select2.Full"
Cohesion: 0.13
Nodes (18): AnalystEditUserPage(), backButtonStyle, badgeStyle, containerStyle(), emptyForm, emptyStateStyle, fieldStyle, formGridStyle() (+10 more)

### Community 81 - "Select2.Full.Min"
Cohesion: 0.13
Nodes (18): AnalystIngredientsCreateReportPage(), backButtonStyle, cellPrimaryStyle, cellStyle, containerStyle(), emptyStyle, headerRowStyle(), headStyle (+10 more)

### Community 82 - "Admin"
Cohesion: 0.13
Nodes (18): AnalystNewUserPage(), backButtonStyle, badgeStyle, containerStyle(), emptyForm, emptyStateStyle, fieldStyle, formGridStyle() (+10 more)

### Community 83 - "Auth Helpers"
Cohesion: 0.12
Nodes (19): cartListStyle(), cartPanelStyle(), catalogTypeChipStyle(), computeItemTotal(), cryptoRandomId(), EditOrderPage(), feedbackStyle(), getCookie() (+11 more)

### Community 84 - "Consumers"
Cohesion: 0.15
Nodes (16): method_decorator, admin_compras_view(), kitchen_order_status_update_view(), LoginView, _notify_usuario_event(), Avisa por el grupo personal del mesero dueño del pedido (ej: cocina lo marcó…, Historial completo de lotes de compra (VGCompra): de qué proveedor/factura vino…, SessionStatusView (+8 more)

### Community 85 - "Related Object Lookups"
Cohesion: 0.19
Nodes (15): ee(), A(), c(), e(), i(), l(), n(), S() (+7 more)

### Community 86 - "Jquery"
Cohesion: 0.13
Nodes (7): AjaxAdapter(), HidePlaceholder(), InitSelection(), MaximumInputLength(), MinimumInputLength(), Placeholder(), Query()

### Community 89 - "Gastos Views"
Cohesion: 0.14
Nodes (16): AnalystEditIngredientPage(), containerStyle(), emptyForm, emptyStyle, fieldStyle, gridStyle(), helpTextStyle, inputStyle (+8 more)

### Community 90 - "Tests"
Cohesion: 0.14
Nodes (17): AnalystNewMesaPage(), backButtonStyle, badgeStyle, containerStyle(), emptyForm, estadoOptions, fieldStyle, formGridStyle() (+9 more)

### Community 91 - "Analyst Inventory Hub Page"
Cohesion: 0.14
Nodes (15): backButtonStyle, ComprobantePagoPage(), containerStyle(), emptyStyle, errorStyle, firmaBoxStyle, firmaRowStyle(), formatUsdBs() (+7 more)

### Community 92 - "Core"
Cohesion: 0.18
Nodes (17): addCombinator(), assert(), compile(), condense(), createPositionalPseudo(), elementMatcher(), find(), markFunction() (+9 more)

### Community 93 - "Jquery"
Cohesion: 0.22
Nodes (3): AttachBody(), CloseOnSelect(), EventRelay()

### Community 94 - "Seed Tequenos La Vara"
Cohesion: 0.18
Nodes (15): DjangoUserAdmin, register, VGCompraPanel, VGDetalleCompraSeccion, VGDetallePedidoSeccion, VGIngredientePanel, VGPagoSeccion, VGPedidoPanel (+7 more)

### Community 95 - "Auth Form"
Cohesion: 0.13
Nodes (15): ajusteItemButtonStyle(), backButtonStyle(), CheckoutPage(), containerStyle(), docButtonsRowStyle(), formatFechaHora(), formatOrderTime(), getCookie() (+7 more)

### Community 96 - "Actions"
Cohesion: 0.18
Nodes (6): AsyncWebsocketConsumer, ASGI config for config project. It exposes the ASGI callable as a module-level…, database_sync_to_async, _get_user_role_name(), PedidosConsumer, Socket único para todo el equipo autenticado. Cada usuario se une a su propio…

### Community 97 - "Calendar"
Cohesion: 0.24
Nodes (10): addPopupIndex(), dismissAddRelatedObjectPopup(), dismissChangeRelatedObjectPopup(), dismissDeleteRelatedObjectPopup(), dismissRelatedLookupPopup(), removePopupIndex(), showAdminPopup(), showRelatedObjectLookupPopup() (+2 more)

### Community 98 - "Confirm Modal"
Cohesion: 0.15
Nodes (14): adoptValue(), ajaxConvert(), ajaxHandleResponses(), Animation(), camelCase(), createFxNow(), createTween(), defaultPrefilter() (+6 more)

### Community 99 - "Tests"
Cohesion: 0.26
Nodes (14): c(), I(), L(), N(), ne(), o(), Q(), re() (+6 more)

### Community 100 - "Restaurant"
Cohesion: 0.18
Nodes (12): AnalystComprasPage(), backButtonStyle, cardHeaderButtonStyle, cardStyle, containerStyle(), detailWrapStyle, emptyStateStyle, errorStyle (+4 more)

### Community 101 - "Analyst Edit Product Page"
Cohesion: 0.18
Nodes (12): AnalystConfiguracionCosteoPage(), backButtonStyle, containerStyle(), emptyStyle, fieldStyle, hintStyle, inputStyle, labelStyle (+4 more)

### Community 102 - "Analyst New Product Page"
Cohesion: 0.15
Nodes (3): AdminCatalogApiTests, Regresión: el frontend real siempre manda contenido_envase/peso_real (con su…, Ver _costo_unitario_por_compra vs. la división simple: reponer stock desde…

### Community 103 - "Unsaved Changes Modal"
Cohesion: 0.21
Nodes (11): AnalystInventoryHubPage(), backButtonStyle, cardButtonStyle, cardDescriptionStyle, cardLinkStyle, cardTitleStyle, containerStyle(), gridStyle() (+3 more)

### Community 104 - "Kitchen Ticket"
Cohesion: 0.35
Nodes (8): clearActiveGuard(), forceClearActiveGuard(), hasActiveGuard(), runWithActiveGuard(), setActiveGuard(), consumeSuppressedPopState(), useUnsavedChangesGuard(), useViewHistory()

### Community 106 - "Settings"
Cohesion: 0.20
Nodes (12): buildFragment(), buildParams(), cloneCopyEvent(), disableScript(), DOMEval(), domManip(), getAll(), isArrayLike() (+4 more)

### Community 107 - "1785330845640.Jpg"
Cohesion: 0.26
Nodes (6): Command, _DryRunAbort, BaseCommand, Exception, Reemplaza a get_or_create(nombre=...) con un chequeo explícito de duplicados:…, Señal interna para deshacer la transacción en modo --dry-run sin marcarlo como…

### Community 108 - "Currency"
Cohesion: 0.25
Nodes (6): App(), AuthForm(), inputStyle, ScreenShell(), SplashScreen(), updateSW

### Community 109 - "Pagination"
Cohesion: 0.38
Nodes (8): checker(), clearAcross(), hide(), reset(), show(), showClear(), showQuestion(), updateCounter()

### Community 110 - "Jquery"
Cohesion: 0.20
Nodes (9): actionButtonStyle, baseCardStyle, closeButtonStyle, errorCardStyle, iconStyle, successCardStyle, textStyle, Toast() (+1 more)

### Community 111 - "Serializers"
Cohesion: 0.20
Nodes (8): calendarMonth(), onClick(), kt(), m(), Tt(), Ut(), b(), D()

### Community 113 - "Seed Restaurant Data"
Cohesion: 0.22
Nodes (5): TestCase, EstadoResultadosHistoricoAcumuladoTests, El negocio ya no maneja kg/l: el catálogo de unidades solo admite…, El total en bolívares de un reporte que abarca varios registros con tasas…, UnidadesMedidaTests

### Community 114 - "0013 Metodos Pago Dinamicos Y Rol Cajera"
Cohesion: 0.25
Nodes (4): Simula "la tasa BCV actual del sistema" para un test: obtener_tasa_actual()…, Un registro ya creado no debe cambiar de valor en bolívares cuando la tasa BCV…, _set_tasa_actual(), TasaCambioInmutabilidadFinancieraTests

### Community 116 - "Select2.Full"
Cohesion: 0.29
Nodes (8): AnalystEditProductPage(), composerRowStyle(), containerStyle(), crearGrupoOpcionVacio(), formGridStyle(), headerRowStyle(), nextOpcionesUid(), titleStyle()

### Community 117 - "Tests"
Cohesion: 0.29
Nodes (8): AnalystNewProductPage(), composerRowStyle(), containerStyle(), crearGrupoOpcionVacio(), formGridStyle(), headerRowStyle(), nextOpcionesUid(), titleStyle()

### Community 118 - "Ing"
Cohesion: 0.46
Nodes (6): BsAmount(), formatSaldoUsdBs(), formatUsdBs(), bsFormatter, formatBs(), formatBsRaw()

### Community 119 - "Seed Carnes Pollos"
Cohesion: 0.50
Nodes (7): buildKitchenTicketHtml(), escapeHtml(), formatTicketTime(), normalizeTicket(), printKitchenTicket(), renderTicketItem(), tipoPedidoLabel()

### Community 120 - "Tests"
Cohesion: 0.29
Nodes (4): _load_env_file(), Django settings for config project. Generated by 'django-admin startproject'…, Load simple KEY=VALUE pairs from a local .env file if present., Path

### Community 121 - "Ajax-Form"
Cohesion: 0.38
Nodes (7): Frontend Public Assets Directory, Stylized Bull Head Icon (red cracked-texture horns), LaVara Grill Logo, Crossed Skewers with Flame Icon, Tagline: Carnes al Fuego en Vara, LAVARA GRILL Wordmark, VaraGrill Project (sistemaVaraGrill)

### Community 122 - "Unit Conversion"
Cohesion: 0.29
Nodes (7): boxModelAdjustment(), createButtonPseudo(), createInputPseudo(), curCSS(), getWidthOrHeight(), manipulationTarget(), nodeName()

### Community 126 - "Tests"
Cohesion: 0.38
Nodes (5): Migration, rescale_forward(), Reescalado de kg/l a g/ml para el catálogo de unidades de inventario (ver…, Reescala en el sitio (guarda cada fila) y devuelve un dict con cuántas filas…, rescale_legacy_units()

### Community 127 - "Kitchen Orders Page"
Cohesion: 0.33
Nodes (6): AnalystPreparationsPage(), componentComposerStyle(), containerStyle(), formGridStyle(), headerRowStyle(), titleStyle()

### Community 129 - "Select2.Full"
Cohesion: 0.33
Nodes (6): admin_ingredientes_bulk_create_view(), _crear_ingredientes_simple(), _preview_ingrediente_simple_row(), Clasifica una fila para la carga masiva SIN costo/cantidad (alta inicial de…, Crea ingredientes nuevos sin stock, costo ni proveedor — solo para dejar…, Carga masiva de ingredientes SIN costo ni cantidad/unidad, pensada para el…

### Community 132 - "0002 Seed Roles"
Cohesion: 0.33
Nodes (5): backfill_tasa_cambio_referencia(), Migration, noop_reverse(), Los registros de egresos/pagos creados antes de este campo existir se quedarian…, No hay nada que deshacer: el AddField reverso ya elimina la columna.

### Community 134 - "0023 Seed Categorias Gasto"
Cohesion: 0.50
Nodes (3): RFC-2046, doAjaxSubmit(), replaceDocument()

### Community 135 - "0024 Seed Rol Contador"
Cohesion: 0.40
Nodes (4): convertirCantidad(), UNIT_FAMILY, UNIT_OPTIONS, UNIT_TO_BASE

### Community 136 - "Notifications"
Cohesion: 0.40
Nodes (4): name, private, scripts, build

### Community 140 - "Nav Sidebar"
Cohesion: 0.83
Nodes (3): readStoredPreference(), useKitchenAlerts(), writeStoredPreference()

### Community 141 - "Urlify"
Cohesion: 0.83
Nodes (3): cycleTheme(), initTheme(), setTheme()

### Community 150 - "Bs"
Cohesion: 0.83
Nodes (3): _build_order_message(), _is_enabled(), send_whatsapp_new_order_alert()

### Community 152 - "Hr"
Cohesion: 0.67
Nodes (3): calcularRaciones(), opcionButtonStyle(), OpcionesProductoModal()

### Community 153 - "Lt"
Cohesion: 0.67
Nodes (3): calcularRaciones(), opcionButtonStyle(), OpcionesProductoModal()

## Knowledge Gaps
- **1513 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+1508 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2170 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **76 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `useUnsavedChangesGuard()` connect `Kitchen Ticket` to `Jquery-3.7.1.Min`, `Api Views`, `Analyst Edit Product Page`, `Analyst Edit Recipe Page`, `Jquery`, `Analyst Products Page`, `Select2.Full`, `Contabilidad Panel Page`, `Select2.Full`, `Analyst New Preparation Page`, `Analyst Ingredients Bulk Create Page`, `Analyst New Chef Recommendation Page`, `Analyst New Ingredient Page`, `Historial Facturas Page`, `Kitchen Orders Page`, `Analyst New User Page`, `Comprobante Pago Page`, `Edit Order Page`, `Jquery`, `Select2.Full`, `Admin`, `Auth Helpers`, `Gastos Views`, `Tests`, `Select2.Full`, `Tests`?**
  _High betweenness centrality (0.015) - this node is a cross-community bridge._
- **Why does `BsAmount()` connect `Ing` to `Historial Facturas Page`, `Jquery-3.7.1.Min`, `Analyst Ingredients Page`, `Facturacion Views`, `Analys Printers Page`, `Analyst Edit Mesa Page`, `Compras Views`, `Api Views`, `Chef Recommendations Page`, `Mesas Atendidas Page`, `Jquery`, `Analyst New Preparation Page`, `Select2.Full`, `Analyst Margen Ganancia Page`, `Analyst New Ingredient Page`?**
  _High betweenness centrality (0.008) - this node is a cross-community bridge._
- **Why does `useToast()` connect `Gastos Views` to `Analyst Ingredients Page`, `Analyst Bulk Promotion Page`, `Analyst Chef Recommendations Page`, `Xregexp.Min`, `Select2.Full`, `Requirements.Txt`, `Analyst New Preparation Page`, `Analyst Recipes Page`, `Cuentas Por Cobrar Page`, `Package.Json`, `Analyst New Ingredient Page`, `Historial Facturas Page`, `Kitchen Orders Page`, `Comprobante Pago Page`, `Jquery`, `Select2.Full`, `Select2.Full.Min`, `Admin`, `Tests`, `Kitchen Orders Page`?**
  _High betweenness centrality (0.007) - this node is a cross-community bridge._
- **What connects `Migration`, `Migration`, `Migration` to the rest of the system?**
  _1513 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `New Order Page` be split into smaller, more focused modules?**
  _Cohesion score 0.043036621224271585 - nodes in this community are weakly interconnected._
- **Should `Jquery-3.7.1.Min` be split into smaller, more focused modules?**
  _Cohesion score 0.023255813953488372 - nodes in this community are weakly interconnected._
- **Should `Edit Order Page` be split into smaller, more focused modules?**
  _Cohesion score 0.05802469135802469 - nodes in this community are weakly interconnected._