import React, { Component } from 'react';
import {
  Button, Input, FileInput, SpaceBetween, Container, Header,
  Cards, Badge, Spinner, Toggle, Box, Select
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
    };
  }

  handleSearch = async () => {
    const { queryText, queryImageFile, backend, searchTargets, topK } = this.state;
    if (!queryText && !queryImageFile) return;

    this.setState({ loading: true, results: [] });

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

    try {
      const response = await FetchPost('/products/search', {
        query_text: queryText,
        query_image_base64: queryImageBase64,
        query_image_format: queryImageFormat,
        backend: backend.value,
        search_targets: searchTargets,
        top_k: topK,
        include_image_url: true,
      }, 'ProductService');

      const body = response?.body || response;
      this.setState({ results: body?.results || [] });
    } catch (e) {
      console.error('Search error:', e);
    } finally {
      this.setState({ loading: false });
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

  render() {
    const { queryText, queryImagePreview, results, loading, backend } = this.state;

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
              <Select
                selectedOption={backend}
                onChange={({ detail }) => this.setState({ backend: detail.selectedOption })}
                options={[
                  { value: 's3vectors', label: 'S3 Vectors' },
                  { value: 'opensearch', label: 'OpenSearch (Phase 2)', disabled: true },
                ]}
              />
              <Button variant="primary" onClick={this.handleSearch} loading={loading}>検索</Button>
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

        {loading && <Spinner size="large" />}

        {results.length > 0 && (
          <Cards
            cardDefinition={{
              header: (item) => (
                <SpaceBetween direction="horizontal" size="xs">
                  <span>{item.product_name}</span>
                  <Badge color={item.match_type === 'image' ? 'blue' : 'green'}>
                    {item.match_type}
                  </Badge>
                </SpaceBetween>
              ),
              sections: [
                {
                  id: 'image',
                  content: (item) => item.image_url
                    ? <img src={item.image_url} alt={item.product_name} style={{ width: '100%', maxHeight: 200, objectFit: 'contain', borderRadius: 4 }} />
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
            items={results}
            cardsPerRow={[{ cards: 1 }, { minWidth: 400, cards: 2 }, { minWidth: 800, cards: 3 }]}
            header={<Header counter={`(${results.length}件)`}>検索結果</Header>}
          />
        )}
      </SpaceBetween>
    );
  }
}

export default ProductSearchPanel;
