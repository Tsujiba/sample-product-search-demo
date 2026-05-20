import React, { Component } from 'react';
import {
  Button, Input, FileInput, SpaceBetween, Container, Header,
  Cards, Badge, Spinner, Toggle, Box, Select, Grid, ColumnLayout
} from '@cloudscape-design/components';
import { FetchPost } from '../../resources/data-provider';

class ProductSearchPanel extends Component {
  constructor(props) {
    super(props);
    this.state = {
      queryText: '',
      queryImageFile: null,
      queryImagePreview: null,
      results: [],
      loading: false,
      backend: { value: 's3vectors', label: 'S3 Vectors' },
      searchTargets: ['image', 'text'],
      topK: 10,
      // 精度比較モード
      compareMode: false,
      resultsA: [],
      resultsB: [],
      loadingCompare: false,
    };
  }

  handleSearch = async () => {
    const { queryText, queryImageFile, searchTargets, topK, compareMode } = this.state;
    if (!queryText && !queryImageFile) return;

    let queryImageBase64 = '';
    let queryImageFormat = 'jpeg';
    if (queryImageFile) {
      const reader = new FileReader();
      const b64 = await new Promise((resolve) => {
        reader.onload = (e) => resolve(e.target.result.split(',')[1]);
        reader.readAsDataURL(queryImageFile);
      });
      queryImageBase64 = b64;
      queryImageFormat = queryImageFile.type.split('/')[1] || 'jpeg';
    }

    const basePayload = {
      query_text: queryText,
      query_image_base64: queryImageBase64,
      query_image_format: queryImageFormat,
      search_targets: searchTargets,
      top_k: topK,
      include_image_url: true,
    };

    if (compareMode) {
      this.setState({ loadingCompare: true, resultsA: [], resultsB: [] });
      try {
        const [resA, resB] = await Promise.all([
          FetchPost('/products/search', { ...basePayload, backend: 's3vectors' }, 'ProductService'),
          FetchPost('/products/search', { ...basePayload, backend: 'opensearch' }, 'ProductService'),
        ]);
        this.setState({
          resultsA: (resA?.body || resA)?.results || [],
          resultsB: (resB?.body || resB)?.results || [],
        });
      } catch (e) { console.error('Compare error:', e); }
      finally { this.setState({ loadingCompare: false }); }
    } else {
      this.setState({ loading: true, results: [] });
      try {
        const response = await FetchPost('/products/search', {
          ...basePayload, backend: this.state.backend.value,
        }, 'ProductService');
        this.setState({ results: (response?.body || response)?.results || [] });
      } catch (e) { console.error('Search error:', e); }
      finally { this.setState({ loading: false }); }
    }
  };

  handleImageSelect = (files) => {
    const file = files[0];
    if (!file) return;
    this.setState({ queryImageFile: file });
    const reader = new FileReader();
    reader.onload = (e) => this.setState({ queryImagePreview: e.target.result });
    reader.readAsDataURL(file);
  };

  renderResultCards(items, title) {
    return (
      <Cards
        cardDefinition={{
          header: (item) => (
            <SpaceBetween direction="horizontal" size="xs">
              <span>{item.product_name}</span>
              <Badge color={item.match_type === 'image' ? 'blue' : 'green'}>{item.match_type}</Badge>
            </SpaceBetween>
          ),
          sections: [
            {
              id: 'image',
              content: (item) => item.image_url
                ? <img src={item.image_url} alt={item.product_name} style={{ width: '100%', maxHeight: 160, objectFit: 'contain', borderRadius: 4 }} />
                : <Box color="text-status-inactive">画像なし</Box>
            },
            {
              id: 'info',
              header: '商品情報',
              content: (item) => (
                <SpaceBetween size="xxs">
                  <div><strong>コード:</strong> {item.product_code}</div>
                  <div><strong>カテゴリ:</strong> {item.category}</div>
                  {item.price > 0 && <div><strong>価格:</strong> ¥{item.price.toLocaleString()}</div>}
                  <div><strong>類似度スコア:</strong> {(1 - item.distance).toFixed(3)}</div>
                </SpaceBetween>
              )
            },
            {
              id: 'text',
              header: 'テキスト情報',
              content: (item) => <Box variant="small">{item.text_content}</Box>
            }
          ]
        }}
        items={items}
        cardsPerRow={[{ cards: 1 }, { minWidth: 500, cards: 2 }]}
        header={<Header counter={`(${items.length}件)`}>{title}</Header>}
      />
    );
  }

  render() {
    const { queryText, queryImagePreview, results, loading, backend, compareMode, resultsA, resultsB, loadingCompare } = this.state;

    return (
      <SpaceBetween size="l">
        <Container header={<Header variant="h2">商品検索</Header>}>
          <SpaceBetween size="m">
            <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
              <div style={{ flex: 1 }}>
                <Input
                  placeholder="検索テキスト（例: もこもこの靴下、撥水バッグ）"
                  value={queryText}
                  onChange={({ detail }) => this.setState({ queryText: detail.value })}
                  onKeyDown={({ detail }) => { if (detail.key === 'Enter') this.handleSearch(); }}
                />
              </div>
              <FileInput
                accept="image/*"
                value={this.state.queryImageFile ? [this.state.queryImageFile] : []}
                onChange={({ detail }) => this.handleImageSelect(detail.value)}
              >画像で検索</FileInput>
              {!compareMode && (
                <Select
                  selectedOption={backend}
                  onChange={({ detail }) => this.setState({ backend: detail.selectedOption })}
                  options={[
                    { value: 's3vectors', label: 'S3 Vectors' },
                    { value: 'opensearch', label: 'OpenSearch Serverless' },
                  ]}
                />
              )}
              <Toggle checked={compareMode} onChange={({ detail }) => this.setState({ compareMode: detail.checked })}>
                精度比較
              </Toggle>
              <Button variant="primary" onClick={this.handleSearch} loading={loading || loadingCompare}>検索</Button>
            </div>

            {queryImagePreview && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <img src={queryImagePreview} alt="query" style={{ height: 60, borderRadius: 4 }} />
                <Button variant="icon" iconName="close"
                  onClick={() => this.setState({ queryImageFile: null, queryImagePreview: null })} />
              </div>
            )}
          </SpaceBetween>
        </Container>

        {(loading || loadingCompare) && <Spinner size="large" />}

        {/* 通常モード */}
        {!compareMode && results.length > 0 && this.renderResultCards(results, '検索結果')}

        {/* 精度比較モード */}
        {compareMode && (resultsA.length > 0 || resultsB.length > 0) && (
          <Grid gridDefinition={[{ colspan: 6 }, { colspan: 6 }]}>
            <div>{this.renderResultCards(resultsA, 'S3 Vectors')}</div>
            <div>{this.renderResultCards(resultsB, 'OpenSearch (Hybrid)')}</div>
          </Grid>
        )}
      </SpaceBetween>
    );
  }
}

export default ProductSearchPanel;
