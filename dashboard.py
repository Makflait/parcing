"""
Дашборд аналитики блогеров v1.0
Запуск: streamlit run dashboard.py
"""
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json

# Настройка страницы
st.set_page_config(
    page_title="Blogger Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Кастомный CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
    }
    .stMetric {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=300)  # Кэш на 5 минут
def load_data_from_sheets():
    """Загружает данные из Google Sheets"""
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open('Blogger Stats')

        all_data = []

        for sheet in spreadsheet.worksheets():
            blogger_name = sheet.title
            if blogger_name in ['Sheet1', 'Лист1']:
                continue

            data = sheet.get_all_values()
            if len(data) <= 1:  # Только заголовок или пусто
                continue

            # Заголовки: Платформа, Дата публикации, Последнее обновление, Название, URL, Просмотры, Лайки, Комментарии, Репосты
            for row in data[1:]:
                if len(row) >= 9:
                    try:
                        all_data.append({
                            'blogger': blogger_name,
                            'platform': row[0],
                            'publish_date': row[1],
                            'last_update': row[2],
                            'title': row[3],
                            'url': row[4],
                            'views': int(row[5]) if row[5] else 0,
                            'likes': int(row[6]) if row[6] else 0,
                            'comments': int(row[7]) if row[7] else 0,
                            'shares': int(row[8]) if row[8] else 0
                        })
                    except (ValueError, IndexError):
                        continue

        return pd.DataFrame(all_data)

    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame()


def main():
    # Заголовок
    st.markdown('<h1 class="main-header">📊 Blogger Analytics Dashboard</h1>', unsafe_allow_html=True)

    # Загрузка данных
    with st.spinner('Загрузка данных из Google Sheets...'):
        df = load_data_from_sheets()

    if df.empty:
        st.warning("Нет данных для отображения. Проверьте подключение к Google Sheets.")
        return

    # Sidebar - фильтры
    st.sidebar.header("🎯 Фильтры")

    # Фильтр по блогерам
    bloggers = ['Все'] + sorted(df['blogger'].unique().tolist())
    selected_blogger = st.sidebar.selectbox("Блогер", bloggers)

    # Фильтр по платформе
    platforms = ['Все'] + sorted(df['platform'].unique().tolist())
    selected_platform = st.sidebar.selectbox("Платформа", platforms)

    # Применяем фильтры
    filtered_df = df.copy()
    if selected_blogger != 'Все':
        filtered_df = filtered_df[filtered_df['blogger'] == selected_blogger]
    if selected_platform != 'Все':
        filtered_df = filtered_df[filtered_df['platform'] == selected_platform]

    # Кнопка обновления
    if st.sidebar.button("🔄 Обновить данные"):
        st.cache_data.clear()
        st.rerun()

    # === МЕТРИКИ ===
    st.header("📈 Общая статистика")

    col1, col2, col3, col4 = st.columns(4)

    total_views = filtered_df['views'].sum()
    total_likes = filtered_df['likes'].sum()
    total_videos = len(filtered_df)
    avg_views = int(total_views / total_videos) if total_videos > 0 else 0

    with col1:
        st.metric("👁️ Просмотры", f"{total_views:,}")
    with col2:
        st.metric("❤️ Лайки", f"{total_likes:,}")
    with col3:
        st.metric("🎬 Видео", f"{total_videos:,}")
    with col4:
        st.metric("📊 Среднее", f"{avg_views:,}")

    # Engagement rate
    engagement = (total_likes / total_views * 100) if total_views > 0 else 0
    st.info(f"💡 **Engagement Rate (Лайки/Просмотры):** {engagement:.2f}%")

    # === ГРАФИКИ ===
    st.header("📊 Визуализация")

    tab1, tab2, tab3, tab4 = st.tabs(["По блогерам", "По платформам", "Топ видео", "Динамика"])

    with tab1:
        # Просмотры по блогерам
        blogger_stats = df.groupby('blogger').agg({
            'views': 'sum',
            'likes': 'sum',
            'url': 'count'
        }).reset_index()
        blogger_stats.columns = ['Блогер', 'Просмотры', 'Лайки', 'Видео']
        blogger_stats = blogger_stats.sort_values('Просмотры', ascending=True)

        fig = px.bar(
            blogger_stats,
            x='Просмотры',
            y='Блогер',
            orientation='h',
            title='Просмотры по блогерам',
            color='Просмотры',
            color_continuous_scale='Viridis'
        )
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        # Таблица со статистикой
        st.subheader("📋 Статистика по блогерам")
        blogger_stats_sorted = blogger_stats.sort_values('Просмотры', ascending=False)
        blogger_stats_sorted['Ср. просмотры'] = (blogger_stats_sorted['Просмотры'] / blogger_stats_sorted['Видео']).astype(int)
        st.dataframe(blogger_stats_sorted, use_container_width=True, hide_index=True)

    with tab2:
        col1, col2 = st.columns(2)

        with col1:
            # Pie chart по платформам (видео)
            platform_videos = df.groupby('platform')['url'].count().reset_index()
            platform_videos.columns = ['Платформа', 'Видео']

            fig = px.pie(
                platform_videos,
                values='Видео',
                names='Платформа',
                title='Распределение видео по платформам',
                color_discrete_sequence=['#FF0050', '#FF0000']  # TikTok pink, YouTube red
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Pie chart по платформам (просмотры)
            platform_views = df.groupby('platform')['views'].sum().reset_index()
            platform_views.columns = ['Платформа', 'Просмотры']

            fig = px.pie(
                platform_views,
                values='Просмотры',
                names='Платформа',
                title='Распределение просмотров по платформам',
                color_discrete_sequence=['#FF0050', '#FF0000']
            )
            st.plotly_chart(fig, use_container_width=True)

        # Сравнение платформ по блогерам
        platform_blogger = df.groupby(['blogger', 'platform'])['views'].sum().reset_index()
        fig = px.bar(
            platform_blogger,
            x='blogger',
            y='views',
            color='platform',
            title='Просмотры по платформам для каждого блогера',
            barmode='group',
            color_discrete_map={'YouTube': '#FF0000', 'TikTok': '#FF0050'}
        )
        fig.update_layout(xaxis_title='Блогер', yaxis_title='Просмотры')
        st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("🏆 Топ-10 видео по просмотрам")

        top_videos = filtered_df.nlargest(10, 'views')[['blogger', 'platform', 'title', 'views', 'likes', 'url']]
        top_videos.columns = ['Блогер', 'Платформа', 'Название', 'Просмотры', 'Лайки', 'URL']

        # Добавляем кликабельные ссылки
        top_videos['Ссылка'] = top_videos['URL'].apply(lambda x: f'[Открыть]({x})')

        st.dataframe(
            top_videos[['Блогер', 'Платформа', 'Название', 'Просмотры', 'Лайки']],
            use_container_width=True,
            hide_index=True
        )

        # График топ видео
        fig = px.bar(
            top_videos,
            x='Просмотры',
            y='Название',
            orientation='h',
            color='Блогер',
            title='Топ-10 видео',
            hover_data=['Платформа', 'Лайки']
        )
        fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("📅 Публикации по датам")

        # Преобразуем даты
        df_dates = filtered_df.copy()
        df_dates['date'] = pd.to_datetime(df_dates['publish_date'], errors='coerce')
        df_dates = df_dates.dropna(subset=['date'])

        if not df_dates.empty:
            # Группируем по дате
            daily_stats = df_dates.groupby(df_dates['date'].dt.date).agg({
                'views': 'sum',
                'url': 'count'
            }).reset_index()
            daily_stats.columns = ['Дата', 'Просмотры', 'Видео']

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=daily_stats['Дата'],
                y=daily_stats['Просмотры'],
                mode='lines+markers',
                name='Просмотры',
                line=dict(color='#1f77b4', width=2)
            ))
            fig.update_layout(
                title='Просмотры по датам публикации',
                xaxis_title='Дата',
                yaxis_title='Просмотры',
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)

            # Публикации по месяцам
            df_dates['month'] = df_dates['date'].dt.to_period('M').astype(str)
            monthly = df_dates.groupby('month')['url'].count().reset_index()
            monthly.columns = ['Месяц', 'Видео']

            fig = px.bar(monthly, x='Месяц', y='Видео', title='Количество публикаций по месяцам')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Нет данных о датах публикации")

    # === ДЕТАЛЬНАЯ ТАБЛИЦА ===
    st.header("📋 Все видео")

    # Поиск
    search = st.text_input("🔍 Поиск по названию")
    if search:
        filtered_df = filtered_df[filtered_df['title'].str.contains(search, case=False, na=False)]

    # Сортировка
    sort_col = st.selectbox("Сортировать по", ['views', 'likes', 'comments', 'publish_date'])
    sort_order = st.radio("Порядок", ['По убыванию', 'По возрастанию'], horizontal=True)

    display_df = filtered_df.sort_values(
        sort_col,
        ascending=(sort_order == 'По возрастанию')
    )[['blogger', 'platform', 'title', 'views', 'likes', 'comments', 'publish_date']]

    display_df.columns = ['Блогер', 'Платформа', 'Название', 'Просмотры', 'Лайки', 'Комментарии', 'Дата']

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)

    # Экспорт
    st.download_button(
        label="📥 Скачать CSV",
        data=filtered_df.to_csv(index=False, encoding='utf-8-sig'),
        file_name=f"blogger_stats_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

    # Footer
    st.markdown("---")
    st.markdown(
        f"*Последнее обновление данных: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
